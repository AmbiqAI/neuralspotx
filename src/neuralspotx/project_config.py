"""Helpers for app config, registry assets, and build integration."""

from __future__ import annotations

import argparse
import copy
import importlib.resources as resources
import logging
import os
import re
from collections import OrderedDict
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import yaml

from ._errors import NSXConfigError, NSXToolchainError
from .constants import PACKAGED_PROJECT_NAME, normalize_board
from .metadata import load_registry_lock
from .models import AppConfig, ModuleRegistryOverride, NsxProject, ProjectEntry
from .subprocess_utils import run
from .tooling import JLINK_NAMES, find_segger_tool

_log = logging.getLogger(__name__)


def _write_text_if_changed(path: Path, content: str) -> bool:
    """Write *content* to *path* only when it differs from the current file.

    Returns ``True`` when the file was (re)written. Avoiding a no-op rewrite
    keeps the file mtime stable, which matters for CMake ``CONFIGURE_DEPENDS``
    inputs (e.g. the generated ``modules.cmake``): retouching an unchanged
    file would force a needless reconfigure on every incremental build.
    """

    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except (OSError, UnicodeDecodeError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _load_registry() -> dict[str, Any]:
    registry_resource = resources.files("neuralspotx.data").joinpath("registry.lock.yaml")
    with resources.as_file(registry_resource) as registry_path:
        return load_registry_lock(registry_path)


def _load_workspace_overlay(path: Path) -> dict[str, Any]:
    """Load a workspace registry overlay file (projects/modules mapping)."""

    if not path.is_file():
        raise NSXConfigError(
            f"registry workspace overlay not found: {path} "
            "(check the 'registry.layers' workspace path in nsx.yml)",
            field="registry.layers",
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise NSXConfigError(f"failed to parse registry overlay {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise NSXConfigError(f"registry overlay {path} must be a mapping")
    return data


def _resolve_override_local_paths(
    override: ModuleRegistryOverride,
    *,
    base_dir: Path,
) -> ModuleRegistryOverride:
    """Resolve relative project ``local_path`` values against their authoring context."""

    projects = copy.deepcopy(override.projects)
    for project in projects.values():
        local_path = project.get("local_path")
        if not isinstance(local_path, str) or not local_path:
            continue
        path = Path(local_path).expanduser()
        if not path.is_absolute():
            path = base_dir / path
        project["local_path"] = str(path.resolve())
    return ModuleRegistryOverride(projects=projects, modules=copy.deepcopy(override.modules))


def _iter_registry_layers(
    nsx_cfg: dict[str, Any], app_dir: Path | None
) -> list[tuple[str, str, ModuleRegistryOverride]]:
    """Resolve the ordered ``registry.layers`` block into labeled overrides.

    Each layer is one of:

    * ``packaged`` — the shipped base registry (a no-op marker; the base
      registry is always the starting point).
    * ``{workspace: <path>}`` — a YAML overlay file with ``projects`` /
      ``modules`` mappings, resolved relative to the app directory (or the
      current working directory when no app context is available).
    * ``{inline: {projects: ..., modules: ...}}`` — an inline override,
      identical in shape to the legacy ``module_registry`` block.

    Layers apply in declared order (last wins). The legacy top-level
    ``module_registry`` block, if present, is applied *after* all layers by
    the caller, preserving its historical highest precedence.

    Returns ``(label, field_prefix, override)`` triples: the label names the
    authoring location for log diagnostics (e.g.
    ``registry.layers[1] (workspace: ../x.yaml)``); the field prefix is the
    dot-path root for :class:`NSXConfigError` ``field`` values (e.g.
    ``registry.layers[1]``).
    """

    registry_cfg = nsx_cfg.get("registry")
    if not isinstance(registry_cfg, dict):
        return []
    layers = registry_cfg.get("layers")
    if layers is None:
        return []
    if not isinstance(layers, list):
        raise NSXConfigError("nsx.yml: 'registry.layers' must be a list")

    base_dir = app_dir if app_dir is not None else Path.cwd()
    resolved: list[tuple[str, str, ModuleRegistryOverride]] = []
    for index, layer in enumerate(layers):
        if isinstance(layer, str):
            if layer == "packaged":
                continue
            raise NSXConfigError(
                f"nsx.yml: unknown registry layer '{layer}' at index {index} "
                "(expected 'packaged' or a {workspace: ...} / {inline: ...} mapping)",
                field=f"registry.layers[{index}]",
            )
        if not isinstance(layer, dict) or len(layer) != 1:
            raise NSXConfigError(
                f"nsx.yml: 'registry.layers[{index}]' must be 'packaged' or a "
                "single-key mapping ({workspace: ...} or {inline: ...}).",
                field=f"registry.layers[{index}]",
            )
        ((kind, value),) = layer.items()
        if kind == "packaged":
            continue
        if kind == "workspace":
            overlay_path = (base_dir / str(value)).resolve()
            resolved.append(
                (
                    f"registry.layers[{index}] (workspace: {value})",
                    f"registry.layers[{index}]",
                    _resolve_override_local_paths(
                        ModuleRegistryOverride.from_mapping(_load_workspace_overlay(overlay_path)),
                        base_dir=overlay_path.parent,
                    ),
                )
            )
        elif kind == "inline":
            resolved.append(
                (
                    f"registry.layers[{index}] (inline)",
                    f"registry.layers[{index}]",
                    _resolve_override_local_paths(
                        ModuleRegistryOverride.from_mapping(value),
                        base_dir=base_dir,
                    ),
                )
            )
        else:
            raise NSXConfigError(
                f"nsx.yml: unknown registry layer kind '{kind}' at index {index} "
                "(expected 'packaged', 'workspace', or 'inline')",
                field=f"registry.layers[{index}]",
            )
    return resolved


# Cross-layer stomp warnings, deduplicated process-wide. ``_effective_registry``
# is recomputed at many call sites per command (lock, sync, discovery, module
# ops), so one real stomp would otherwise repeat once per recomputation. The
# key is the full warning content — (module, pinned revision, winning revision,
# winning layer) — so only literally identical repeats are suppressed: a
# genuinely different stomp (any element differing) always warns. The registry
# is bounded LRU-style so long-running embedders that resolve many manifests
# cannot grow it without limit; eviction can at worst repeat an old warning,
# never suppress a new one. Unlocked by design: the GIL keeps the OrderedDict
# operations coherent, and the worst concurrent-race outcome is one duplicate
# warning line.
_PIN_STOMP_WARNED: OrderedDict[tuple[str, str, str, str], None] = OrderedDict()
_PIN_STOMP_WARNED_MAX = 256


def _should_warn_pin_stomp(key: tuple[str, str, str, str]) -> bool:
    """True exactly once per distinct stomp-warning content per process."""

    if key in _PIN_STOMP_WARNED:
        _PIN_STOMP_WARNED.move_to_end(key)
        return False
    _PIN_STOMP_WARNED[key] = None
    while len(_PIN_STOMP_WARNED) > _PIN_STOMP_WARNED_MAX:
        _PIN_STOMP_WARNED.popitem(last=False)
    return True


def _reset_pin_stomp_warnings() -> None:
    """Forget which stomp warnings were already emitted (test isolation hook)."""

    _PIN_STOMP_WARNED.clear()


def _propagate_layer_project_pins(
    merged: dict[str, Any],
    layer: ModuleRegistryOverride,
    *,
    layer_label: str,
    field_prefix: str,
    app_pinned_modules: dict[str, str],
    propagated_revisions: dict[str, str],
) -> None:
    """Make *layer*'s project-level ``revision`` pins effective for its modules.

    ``registry_entry_for_module`` selects revisions from the module-level
    ``modules.<name>.revision`` field only, so without this step an
    app-authored ``projects.<p>.revision`` pin is silently outranked by the
    *packaged* registry's module-level defaults — a lower-precedence source
    winning over an explicit app pin (issue #218).

    Precedence contract:

    * **Across sources** an app-authored layer beats the packaged registry
      (and the synthetic profile defaults): a layer that pins a project's
      revision repins every module of that project in the merged view.
    * **Within one source** module-level beats project-level: a module the
      *same layer* pins with an explicit non-empty ``revision`` keeps that
      pin (starter-profile emissions and monorepo per-module pins rely on
      this).
    * **Between app-authored layers** the later layer wins even against an
      earlier layer's explicit module-level pin — but because that trades a
      specific pin for a general one, the stomp is logged as a warning
      naming the module, both revisions, and the winning layer (deduplicated
      process-wide by content, see :func:`_should_warn_pin_stomp`).

    ``app_pinned_modules`` is the caller-owned provenance map of module name
    to the revision an *explicit* module-level pin in an app-authored layer
    gave it. The stomp warning quotes that tracked value — not the merged
    entry's current one — so a same-layer erasure (``revision: ""``) cannot
    misreport the earlier pin. Entries this function overwrites are removed;
    the layer's own explicit pins are recorded at the end. Silently
    overwriting packaged/profile-sourced revisions is the fix working as
    intended and stays warning-free.

    ``propagated_revisions`` is the caller-owned provenance map of module
    name to the revision value that propagation *replaced* (first
    propagation wins across chained layers). :func:`_apply_app_authored_layer`
    consumes it to un-propagate a pin when a later layer re-points the
    module to a different project.

    A project override that carries a ``revision`` key with a non-string
    value raises :class:`NSXConfigError` — an unquoted YAML scalar such as
    ``revision: 1.0`` would otherwise be a silently dead pin, the same
    footgun class as issue #218 (module-level entries already fail loud in
    ``registry_entry_for_module``).

    Only ``revision`` is propagated, and only onto modules whose (post-merge)
    ``project`` names the pinned project. Mutates *merged* in place; called
    once per app-authored layer, immediately after that layer merges.
    """

    modules = merged.get("modules")
    if not isinstance(modules, dict):
        modules = {}
    for project_name, project_override in layer.projects.items():
        revision = project_override.get("revision")
        if "revision" in project_override and not isinstance(revision, str):
            remedy = (
                "Remove the empty 'revision:' key (or quote a real ref)."
                if revision is None
                else "Quote the value in YAML so the pin is honored."
            )
            raise NSXConfigError(
                f"{layer_label}: projects.{project_name}.revision must be a "
                f"string, got {type(revision).__name__} ({revision!r}). {remedy}",
                field=f"{field_prefix}.projects.{project_name}.revision",
            )
        if not isinstance(revision, str) or not revision:
            continue
        for module_name, module_entry in modules.items():
            if not isinstance(module_entry, dict):
                continue
            if module_entry.get("project") != project_name:
                continue
            layer_module = layer.modules.get(module_name)
            if isinstance(layer_module, dict):
                layer_revision = layer_module.get("revision")
                if isinstance(layer_revision, str) and layer_revision:
                    # Same-source module-level pin outranks its project pin.
                    continue
            pinned = app_pinned_modules.get(module_name)
            if pinned is not None and pinned != revision:
                if _should_warn_pin_stomp((module_name, pinned, revision, layer_label)):
                    _log.warning(
                        "module '%s': revision '%s' was pinned module-level by an "
                        "earlier app-authored override layer, but %s pins project "
                        "'%s' at '%s', which takes precedence (later app-authored "
                        "layers outrank earlier ones). Add a module-level "
                        "'modules.%s.revision' override to %s to keep a "
                        "module-specific pin.",
                        module_name,
                        pinned,
                        layer_label,
                        project_name,
                        revision,
                        module_name,
                        layer_label,
                    )
                app_pinned_modules.pop(module_name)
                pinned = None
            if pinned is None:
                # Remember what propagation replaced (first write wins across
                # chained layers) so a later project re-point can restore it.
                current = module_entry.get("revision")
                if isinstance(current, str) and current:
                    propagated_revisions.setdefault(module_name, current)
            module_entry["revision"] = revision
    for module_name, layer_module in layer.modules.items():
        layer_revision = layer_module.get("revision")
        if isinstance(layer_revision, str) and layer_revision:
            app_pinned_modules[module_name] = layer_revision


def _apply_app_authored_layer(
    merged: dict[str, Any],
    layer: ModuleRegistryOverride,
    *,
    layer_label: str,
    field_prefix: str,
    app_pinned_modules: dict[str, str],
    propagated_revisions: dict[str, str],
) -> dict[str, Any]:
    """Merge one app-authored override layer and apply its pin semantics.

    Wraps ``layer.merge_into`` with the revision-provenance bookkeeping that
    cross-source pin precedence needs:

    1. snapshot each layer-touched module's pre-merge ``project``;
    2. merge the layer;
    3. drop propagated-revision provenance for modules the layer authored a
       ``revision`` for (an authored value replaced the propagated one);
    4. un-propagate on re-point: a layer that changes a module's ``project``
       without expressing a ``revision`` restores the value propagation had
       replaced — a propagated pin is scoped to the project it came from and
       must not leak onto the module's new project (its explicit module-level
       pins, being module-scoped, do survive a re-point);
    5. propagate this layer's project pins (:func:`_propagate_layer_project_pins`).
    """

    prev_projects: dict[str, Any] = {}
    modules_before = merged.get("modules")
    if isinstance(modules_before, dict):
        for name in layer.modules:
            entry = modules_before.get(name)
            if isinstance(entry, dict):
                prev_projects[name] = entry.get("project")

    merged = layer.merge_into(merged)

    modules = merged.get("modules")
    modules = modules if isinstance(modules, dict) else {}
    for name, override in layer.modules.items():
        if "revision" in override:
            # The layer authored a revision value (even an empty one): the
            # propagated value is gone, so its restore provenance is too.
            propagated_revisions.pop(name, None)
            continue
        if name not in propagated_revisions or "project" not in override:
            continue
        entry = modules.get(name)
        if isinstance(entry, dict) and entry.get("project") != prev_projects.get(name):
            entry["revision"] = propagated_revisions.pop(name)

    _propagate_layer_project_pins(
        merged,
        layer,
        layer_label=layer_label,
        field_prefix=field_prefix,
        app_pinned_modules=app_pinned_modules,
        propagated_revisions=propagated_revisions,
    )
    return merged


def _effective_registry(
    base_registry: dict[str, Any],
    nsx_cfg: dict[str, Any],
    *,
    app_dir: Path | None = None,
) -> dict[str, Any]:
    """Fold the registry layer stack onto *base_registry*.

    Precedence (lowest to highest): packaged base registry, synthetic starter
    profile defaults, each ``registry.layers`` entry in order, then the legacy
    ``module_registry`` block. This keeps explicit workspace/inline development
    layers above implicit profile defaults while preserving the historical
    highest precedence of authored app-local overrides.

    App-authored layers (``registry.layers`` entries and the ``module_registry``
    block) additionally have their project-level ``revision`` pins propagated
    onto the project's modules (see :func:`_propagate_layer_project_pins`), so
    an explicit app pin cannot be silently outranked by a lower-precedence
    source's module-level default. When that propagation overrides a module
    revision an *earlier* app-authored layer pinned explicitly, a warning is
    logged (layer precedence beats specificity, but never silently). The
    synthetic profile defaults are derived from the packaged registry — the
    same source — so they merge without propagation and their explicit
    per-module pins keep their historical meaning.
    """

    merged = ModuleRegistryOverride.from_mapping(nsx_cfg.get("_profile_registry")).merge_into(
        base_registry
    )
    # Revision provenance across app-authored layers: which modules carry an
    # explicit module-level pin (and its value, for the stomp warning), and
    # which carry a propagated project pin (and the value it replaced, for
    # un-propagation when a later layer re-points the module).
    app_pinned_modules: dict[str, str] = {}
    propagated_revisions: dict[str, str] = {}
    for label, field_prefix, layer in _iter_registry_layers(nsx_cfg, app_dir):
        merged = _apply_app_authored_layer(
            merged,
            layer,
            layer_label=label,
            field_prefix=field_prefix,
            app_pinned_modules=app_pinned_modules,
            propagated_revisions=propagated_revisions,
        )
    app_override = _resolve_override_local_paths(
        ModuleRegistryOverride.from_mapping(nsx_cfg.get("module_registry")),
        base_dir=app_dir if app_dir is not None else Path.cwd(),
    )
    return _apply_app_authored_layer(
        merged,
        app_override,
        layer_label="module_registry",
        field_prefix="module_registry",
        app_pinned_modules=app_pinned_modules,
        propagated_revisions=propagated_revisions,
    )


def validate_app_module_alignment(
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
) -> None:
    """Guard against partial project migrations in an app manifest.

    When an app's ``modules:`` list pins a module to a ``project:`` (e.g.
    after migrating onto a consolidated SDK bundle), the *effective*
    registry must resolve that module to the **same** project. A mismatch
    means the module-level override under ``module_registry.modules`` was
    forgotten, so resolution silently falls back to the base registry's
    (often stale) project — the exact failure mode that breaks
    ``nsx sync``/build long after the manifest was edited.

    Raised early (at lock/sync time) with a precise, per-module message so
    the partial migration is caught at author time rather than as an opaque
    "Unable to locate nsx-module.yaml" failure deep in resolution.
    """

    from .metadata import registry_entry_for_module

    app = AppConfig.from_mapping(nsx_cfg)
    mismatches: list[str] = []
    for module in app.modules:
        if module.project is None or module.is_opaque:
            continue
        try:
            entry = registry_entry_for_module(registry, module.name)
        except (KeyError, ValueError):
            # A genuinely missing registry entry is diagnosed by the
            # resolver itself; this guard only covers misalignment.
            continue
        if entry.project != module.project:
            mismatches.append(
                f"  - {module.name}: manifest pins project '{module.project}' but the "
                f"registry resolves it to '{entry.project}'"
            )
    if mismatches:
        raise NSXConfigError(
            "nsx.yml: module/project misalignment (partial project migration?).\n"
            + "\n".join(mismatches)
            + "\nAdd a matching 'module_registry.modules.<name>' override (with a "
            "'metadata:' path) for each listed module so it resolves into the "
            "intended project."
        )


def _registry_project_entry(registry: dict[str, Any], project_name: str) -> ProjectEntry:
    projects = registry.get("projects", {})
    if not isinstance(projects, dict):
        return ProjectEntry(name=project_name)
    return ProjectEntry.from_mapping(project_name, projects.get(project_name))


def _source_checkout_version() -> str | None:
    """Return the version declared in a nearby source checkout, if present."""

    for parent in Path(__file__).resolve().parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return None

        in_project = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                in_project = line == "[project]"
                continue
            if not in_project:
                continue
            match = re.match(r'version\s*=\s*["\']([^"\']+)["\']\s*$', line)
            if match:
                return match.group(1)
        return None
    return None


def _nsx_tool_version() -> str | None:
    source_version = _source_checkout_version()
    if source_version:
        return source_version
    try:
        return package_version("neuralspotx")
    except PackageNotFoundError:
        return None


def _nsx_tool_major(version_text: str | None) -> int | None:
    if not version_text:
        return None
    head = version_text.split(".", 1)[0]
    return int(head) if head.isdigit() else None


def _check_nsx_version_compatibility(cfg: dict[str, Any], cfg_path: Path) -> None:
    tooling = cfg.get("tooling", {})
    if not isinstance(tooling, dict):
        return
    nsx_info = tooling.get("nsx", {})
    if not isinstance(nsx_info, dict):
        return

    recorded_major = nsx_info.get("major")
    if not isinstance(recorded_major, int):
        return

    current_version = _nsx_tool_version()
    current_major = _nsx_tool_major(current_version)
    if current_major is None or recorded_major == current_major:
        return

    if os.getenv("NSX_ALLOW_VERSION_MISMATCH"):
        return

    recorded_version = nsx_info.get("version")
    raise NSXConfigError(
        f"{cfg_path}: app was created with nsx {recorded_version or recorded_major}, "
        f"but current nsx major version is {current_major}. "
        "Set NSX_ALLOW_VERSION_MISMATCH=1 to bypass this check for now."
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    """Parse *path* as YAML and require a mapping (dict) at the root.

    Empty files, non-mapping roots, and YAML parse errors all surface
    as a deterministic :class:`NSXConfigError` with the offending path
    so the user gets a clear, actionable error rather than an opaque
    ``AttributeError`` deep in a ``.get()`` call later on.
    """

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise NSXConfigError(f"{path}: invalid YAML: {exc}") from None
    if loaded is None:
        raise NSXConfigError(f"{path}: file is empty or contains only comments")
    if not isinstance(loaded, dict):
        raise NSXConfigError(
            f"{path}: expected a YAML mapping at the root, got {type(loaded).__name__}"
        )
    return loaded


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _copy_packaged_tree(package: str, relative_path: str, destination: Path) -> None:
    source_resource = resources.files(package).joinpath(relative_path)
    with resources.as_file(source_resource) as src:
        if destination.exists():
            import shutil

            shutil.rmtree(destination)
        import shutil

        shutil.copytree(
            src,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__"),
        )


def _write_cmake_nsx_gitignore(app_dir: Path) -> None:
    """Gitignore the regenerated ``cmake/nsx/`` build-glue tree.

    The entire ``cmake/nsx/`` directory is reproduced from the pinned
    ``neuralspotx`` package on every ``nsx lock`` / ``nsx sync`` (see
    ``_copy_packaged_tree`` plus the ``modules.cmake`` overlay), so it is
    machine-generated and should not be committed. The ignore rule is
    written to the app-owned ``cmake/.gitignore`` (the parent directory)
    rather than inside ``cmake/nsx/`` so it never perturbs the content
    hash of the regenerated tooling tree.
    """

    cmake_dir = app_dir / "cmake"
    cmake_dir.mkdir(parents=True, exist_ok=True)
    marker = "# Auto-generated by neuralspotx — do not edit."
    rule = "/nsx/"
    gitignore = cmake_dir / ".gitignore"
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8").splitlines()
        if rule in existing:
            return
        lines = existing
        if marker not in existing:
            lines = [marker, *lines]
        lines.append(rule)
        gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    content = (
        f"{marker}\n"
        "# cmake/nsx/ is build glue reproduced from the pinned neuralspotx\n"
        "# package on every `nsx lock` / `nsx sync`; do not commit it.\n"
        f"{rule}\n"
    )
    gitignore.write_text(content, encoding="utf-8")


def _write_app_module_file(
    app_dir: Path,
    nsx_cfg: dict[str, Any],
    *,
    module_names: list[str] | None = None,
) -> None:
    ordered_module_names = module_names or AppConfig.from_mapping(nsx_cfg).module_names()
    registry = _effective_registry(_load_registry(), nsx_cfg, app_dir=app_dir)
    lines = [
        "# Auto-generated by neuralspotx. Included by app CMakeLists.",
        "set(NSX_APP_MODULES",
    ]
    for name in ordered_module_names:
        lines.append(f"    {name}")
    lines.append(")")

    for name in ordered_module_names:
        try:
            source_dir = _module_source_dir_relative_to_app(name, registry, nsx_cfg)
        except (KeyError, ValueError, TypeError):
            continue
        if source_dir.parts[:1] != ("modules",):
            continue
        lines.append(f'set(NSX_APP_MODULE_DIR_{name.replace("-", "_")} "{source_dir.as_posix()}")')

    project_dirs = sorted({
        project_dir.as_posix()
        for name in ordered_module_names
        if (project_dir := _module_project_dir_relative_to_app(name, registry, nsx_cfg)) is not None
    })
    if project_dirs:
        lines.append("")
        lines.append("set(NSX_APP_PROJECT_DIRS")
        for project_dir in project_dirs:
            lines.append(f"    {project_dir}")
        lines.append(")")

    content = "\n".join(lines) + "\n"
    (app_dir / "cmake" / "nsx").mkdir(parents=True, exist_ok=True)
    _write_text_if_changed(app_dir / "cmake" / "nsx" / "modules.cmake", content)


def _write_modules_gitignore(app_dir: Path, nsx_cfg: dict[str, Any]) -> None:
    """Generate ``modules/.gitignore`` to ignore registry modules but keep
    user-owned ones.

    Three categories of modules:
      * Registry (git/packaged) — re-acquired by ``nsx sync``; ignored.
      * Local (``local: true``) — mirrored from external path; ignored.
      * Vendored (``source: { vendored: true }``) — source-controlled with
        the app; NOT ignored.
    """

    _write_modules_gitignore_for_module_names(
        app_dir,
        nsx_cfg,
        AppConfig.from_mapping(nsx_cfg).module_names(),
    )


def _module_gitignore_relpath(
    app_dir: Path,
    registry: dict[str, Any],
    name: str,
) -> Path:
    """Resolve the ``modules/``-relative directory a module is vendored into.

    Mirrors :func:`_module_source_dir_relative_to_app` /
    :func:`_resolved_module_path`: a module that resolves to a registry
    project is vendored under its project clone dir (``modules/<project>``),
    everything else under ``modules/<name>``.

    Raises ``ValueError`` when the module has no registry entry (or resolves
    outside ``modules/``); callers decide whether that means *skip* (registry
    modules) or *fall back to* ``modules/<name>`` (local modules).
    Malformed-registry ``KeyError`` / ``TypeError`` fall back to ``<name>``.
    """
    from .metadata import registry_entry_for_module

    modules_root = app_dir / "modules"
    try:
        entry = registry_entry_for_module(registry, name)
        if _is_packaged_module(registry, name):
            target_dir = _vendored_target_dir(app_dir, name, entry.metadata)
        else:
            target_dir = _module_clone_dir(app_dir, entry.project, registry)
        return target_dir.relative_to(modules_root)
    except (KeyError, ValueError, TypeError):
        return Path(name)


def _module_gitignore_entries(
    app_dir: Path,
    *,
    nsx_cfg: dict[str, Any],
    module_names: list[str],
    local_names: set[str],
    vendored_names: set[str],
) -> list[str]:
    registry = _effective_registry(_load_registry(), nsx_cfg, app_dir=app_dir)
    entries: list[str] = []
    for name in module_names:
        if name in local_names or name in vendored_names:
            continue
        try:
            rel = _module_gitignore_relpath(app_dir, registry, name)
        except ValueError:
            continue
        if rel.parts:
            entries.append(rel.as_posix().rstrip("/") + "/")
    return _unique_preserving_order(entries)


def _local_module_gitignore_paths(
    app_dir: Path,
    nsx_cfg: dict[str, Any],
    local_names: set[str],
) -> dict[str, str]:
    """Map each local module name to the ``modules/``-relative dir it is
    vendored into.

    A ``local: true`` module that resolves to a registry project whose name
    differs from the module name (e.g. ``nsx-helia-rt`` in project
    ``helia-rt``) is vendored under ``modules/<project>`` by ``nsx sync``, so
    that — not ``modules/<name>`` — is what must be ignored. Bare local
    modules with no registry entry stay at ``modules/<name>``.
    """
    registry = _effective_registry(_load_registry(), nsx_cfg, app_dir=app_dir)
    paths: dict[str, str] = {}
    for name in sorted(local_names):
        try:
            rel = _module_gitignore_relpath(app_dir, registry, name)
        except ValueError:
            # Bare local module with no registry entry — stays at modules/<name>/.
            rel = Path(name)
        paths[name] = rel.as_posix().rstrip("/") + "/"
    return paths


def _write_modules_gitignore_for_names(
    app_dir: Path,
    *,
    registry_entries: list[str],
    local_entries: dict[str, str],
    vendored_names: set[str],
) -> None:
    """Generate ``modules/.gitignore`` for a resolved module set."""

    lines = [
        "# Auto-generated by neuralspotx — do not edit.",
        "# Registry modules are re-acquired by `nsx sync`.",
    ]
    for entry in sorted(registry_entries):
        lines.append(entry)
    if local_entries:
        lines.append("")
        lines.append("# Local modules (mirrored from external path) are ignored:")
        for entry in sorted(set(local_entries.values())):
            lines.append(entry)
    if vendored_names:
        lines.append("")
        lines.append("# Vendored modules (committed in this app) are NOT ignored:")
        for name in sorted(vendored_names):
            lines.append(f"# {name}/  (kept in git)")
    lines.append("")
    (app_dir / "modules").mkdir(parents=True, exist_ok=True)
    _write_text_if_changed(app_dir / "modules" / ".gitignore", "\n".join(lines))


def _write_modules_gitignore_for_module_names(
    app_dir: Path,
    nsx_cfg: dict[str, Any],
    module_names: list[str],
) -> None:
    app_cfg = AppConfig.from_mapping(nsx_cfg)
    local_names = app_cfg.local_module_names()
    vendored_names = app_cfg.vendored_module_names()
    registry_entries = _module_gitignore_entries(
        app_dir,
        nsx_cfg=nsx_cfg,
        module_names=module_names,
        local_names=local_names,
        vendored_names=vendored_names,
    )
    _write_modules_gitignore_for_names(
        app_dir,
        registry_entries=registry_entries,
        local_entries=_local_module_gitignore_paths(app_dir, nsx_cfg, local_names),
        vendored_names=vendored_names,
    )


def _vendored_metadata_relpath(metadata: str) -> Path:
    path = Path(metadata)
    parts = path.parts
    if parts[:1] == ("modules",):
        return path
    if "boards" in parts:
        idx = parts.index("boards")
        return Path(*parts[idx:])
    if "cmake" in parts:
        idx = parts.index("cmake")
        return Path(*parts[idx:])
    if len(parts) >= 2:
        return Path("modules") / parts[0] / Path(*parts[1:])
    return Path("modules") / path


def _vendored_target_dir(app_dir: Path, module_name: str, metadata: str) -> Path:
    rel = _vendored_metadata_relpath(metadata)
    if rel.parts[:1] == ("boards",) and len(rel.parts) >= 2:
        return app_dir / "boards" / rel.parts[1]
    if rel.parts[:1] == ("cmake",):
        return app_dir / "cmake" / "nsx"
    if rel.parts[:1] == ("modules",) and len(rel.parts) >= 2:
        if rel.parts[1].endswith(".yaml") or rel.parts[1].endswith(".yml"):
            return app_dir / "modules" / module_name
        return app_dir / "modules" / rel.parts[1]
    return app_dir / "modules" / module_name


def _metadata_path_relative_to_project(metadata: Path, project_path: str | None) -> Path:
    if not metadata.is_absolute():
        if project_path is not None:
            project_parts = Path(project_path).parts
            if metadata.parts[: len(project_parts)] == project_parts:
                return Path(*metadata.parts[len(project_parts) :])
        return metadata
    return Path(metadata.name)


def _is_packaged_module(registry: dict[str, Any], module_name: str) -> bool:
    """Return whether *module_name* should resolve from packaged content."""

    from .metadata import registry_entry_for_module

    entry = registry_entry_for_module(registry, module_name)
    project = _registry_project_entry(registry, entry.project)
    return entry.project == PACKAGED_PROJECT_NAME and not project.local_path


def _module_clone_dir(app_dir: Path, project_name: str, registry: dict | None = None) -> Path:
    """Return the local clone destination for a module project.

    Uses the project's ``path`` field from the registry when available,
    otherwise falls back to ``modules/<project_name>``.
    """

    if registry is not None:
        project = _registry_project_entry(registry, project_name)
        project_path = project.path
        if project.local_path and (
            not project_path
            or Path(project_path).is_absolute()
            or Path(project_path).parts[:1] != ("modules",)
        ):
            return app_dir / "modules" / project_name
        if project_path:
            return app_dir / project_path

    return app_dir / "modules" / project_name


def _module_source_dir_relative_to_app(
    module_name: str,
    registry: dict[str, Any],
    nsx_cfg: dict[str, Any],
) -> Path:
    """Resolve a module's on-disk directory relative to the app root.

    Git modules are vendored under their *project* clone directory (a whole
    monorepo may host many modules), so the module dir is the project clone
    dir joined with the module's metadata path taken relative to the project
    root. Packaged modules keep their vendored target layout.

    Vendored modules (``source: {vendored: true}``) and bare local modules
    (``local: true`` with no registry entry, e.g. ``nsx module add --local``)
    have no registry project, so their source IS ``modules/<name>``.

    A ``local: true`` module that *does* resolve to a registry project — e.g.
    an engine module pinned to a monorepo project whose name differs from the
    module name (``nsx-helia-rt`` in project ``helia-rt``) — is resolved
    through the project clone dir, then the module's own metadata sub-path
    (``modules/helia-rt/nsx``), exactly like a git module. ``nsx lock`` /
    ``nsx sync`` (via ``_resolved_module_path``) vendor the project clone dir
    itself (``modules/helia-rt``), so this returns a subdirectory of that
    same vendored tree — keeping the generated ``modules.cmake`` module-dir
    map (consumed by the CMake ``add_subdirectory`` bootstrap) pointing inside
    the directory the module is actually vendored into.
    """

    from .metadata import registry_entry_for_module

    app_cfg = AppConfig.from_mapping(nsx_cfg)

    # Vendored modules: the source IS modules/<name>/ (no registry project).
    if module_name in app_cfg.vendored_module_names():
        return Path("modules") / module_name

    try:
        entry = registry_entry_for_module(registry, module_name)
    except ValueError:
        # Bare local module with no registry entry (`nsx module add
        # --local`) — the source IS modules/<name>/.
        if module_name in app_cfg.local_module_names():
            return Path("modules") / module_name
        raise

    if _is_packaged_module(registry, module_name):
        return _vendored_target_dir(Path("."), module_name, entry.metadata)

    project_entry = _registry_project_entry(registry, entry.project)
    metadata_rel = _metadata_path_relative_to_project(Path(entry.metadata), project_entry.path)
    return _module_clone_dir(Path("."), entry.project, registry) / metadata_rel.parent


def _module_project_dir_relative_to_app(
    module_name: str,
    registry: dict[str, Any],
    nsx_cfg: dict[str, Any],
) -> Path | None:
    """Resolve a module's project clone dir (where its bundle-level ``cmake/``
    helpers live), or ``None`` when the module has no registry project.

    Vendored modules and bare local modules (``local: true`` with no registry
    entry) have no project clone dir → ``None``. A ``local: true`` module that
    *does* resolve to a registry project (e.g. ``nsx-helia-rt`` in project
    ``helia-rt``) returns its project clone dir, exactly like a git module, so
    its bundle-level ``cmake/*.cmake`` helpers are made available to the app
    bootstrap. (A self-contained wrapper with no ``cmake/`` helpers is
    harmless: the bootstrap simply globs an empty set.)
    """

    from .metadata import registry_entry_for_module

    app_cfg = AppConfig.from_mapping(nsx_cfg)
    if module_name in app_cfg.vendored_module_names():
        return None
    try:
        entry = registry_entry_for_module(registry, module_name)
    except ValueError:
        # Bare local module with no registry entry — no project clone dir.
        if module_name in app_cfg.local_module_names():
            return None
        raise
    if _is_packaged_module(registry, module_name):
        return None
    return _module_clone_dir(Path("."), entry.project, registry)


def find_app_root(start: Path | None = None) -> Path | None:
    """Walk upward from *start* to find the nearest ``nsx.yml``.

    Stops at the filesystem root or a git repository boundary (a directory
    containing ``.git``).  Returns the resolved directory containing
    ``nsx.yml``, or ``None`` when no app root is found.
    """

    current = (start or Path.cwd()).expanduser().resolve()
    while True:
        if (current / "nsx.yml").exists():
            return current
        # Stop at git boundary — do not cross into a parent repo.
        if (current / ".git").exists():
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def resolve_app_dir(explicit: str | Path | None) -> Path:
    """Return a resolved app directory from an explicit path or upward walk.

    Resolution order when *explicit* is given (and is not ``"."``):

    1. If it points at an existing path, use it directly.
    2. If it is a bare *name* (no path separators) that does not exist as
       a path, try to discover a sibling app of that name under the
       current directory or its ``examples/`` folder. This lets
       ``nsx build hello_world`` work from a repository root that holds
       many app subdirectories.
    3. Otherwise return the path as given (downstream produces a clear
       "nsx.yml not found" error).

    When *explicit* is ``None`` or ``"."``, :func:`find_app_root` searches
    upward from the current directory.
    """

    if explicit is not None and str(explicit) != ".":
        candidate = Path(explicit).expanduser()
        if candidate.exists():
            return candidate.resolve()
        name = str(explicit)
        if os.sep not in name and (os.altsep is None or os.altsep not in name):
            apps = discover_apps()
            match = apps.get(name)
            if match is not None:
                return match
        return candidate.resolve()

    found = find_app_root()
    if found is not None:
        return found
    # Fall back to explicit value (usually ".") so downstream code
    # produces a clear "nsx.yml not found" error.
    return Path(explicit or ".").expanduser().resolve()


def discover_apps(root: Path | None = None) -> dict[str, Path]:
    """Map app name -> directory for ``nsx.yml`` found near *root*.

    Searches the immediate children of *root* (default: the current
    directory) and of ``root/examples``. The directory name is used as
    the app key; on a name collision the first match wins.
    """

    base = (root or Path.cwd()).expanduser().resolve()
    found: dict[str, Path] = {}
    for search_root in (base, base / "examples"):
        if not search_root.is_dir():
            continue
        for child in sorted(search_root.iterdir()):
            if child.is_dir() and (child / "nsx.yml").exists():
                found.setdefault(child.name, child.resolve())
    return found


def _require_app_config(app_dir: Path) -> None:
    """Fail if *app_dir* does not contain an ``nsx.yml``."""

    if (app_dir / "nsx.yml").exists():
        return
    raise NSXConfigError(
        f"NSX app config not found: {app_dir / 'nsx.yml'}\n"
        "Run `nsx create-app <app-dir>` to create a new app."
    )


def _metadata_storage_path(app_dir: Path, metadata_path: Path, project_entry: ProjectEntry) -> str:
    if project_entry.local_path:
        local_root = Path(project_entry.local_path).expanduser().resolve()
        try:
            return str(metadata_path.resolve().relative_to(local_root))
        except ValueError:
            pass

    if project_entry.path:
        clone_dir = app_dir / project_entry.path
        try:
            metadata_rel = metadata_path.resolve().relative_to(clone_dir.resolve())
            return str(Path(project_entry.path) / metadata_rel)
        except ValueError:
            pass

    try:
        return str(metadata_path.resolve().relative_to(app_dir.resolve()))
    except ValueError:
        return str(metadata_path.resolve())


def _packaged_metadata_path(metadata: Path) -> Path | None:
    parts = metadata.parts
    if len(parts) >= 4 and tuple(parts[:2]) == ("src", "neuralspotx") and parts[2] == "boards":
        resource = resources.files("neuralspotx").joinpath("boards", *parts[3:])
    elif len(parts) >= 3 and tuple(parts[:3]) == ("src", "neuralspotx", "cmake"):
        resource = resources.files("neuralspotx").joinpath("cmake", *parts[3:])
    else:
        return None

    with resources.as_file(resource) as resource_path:
        if resource_path.exists():
            return resource_path
    return None


def _unique_preserving_order(module_names: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in module_names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _app_name_from_cfg(nsx_cfg: dict[str, Any]) -> str:
    return AppConfig.from_mapping(nsx_cfg).project_name


def _default_build_dir(app_dir: Path, board: str) -> Path:
    return app_dir / "build" / board


def _lock_board_key(nsx_cfg: dict[str, Any], board: str | None = None) -> str | None:
    """Board key for this app's section of the combined ``nsx.lock``.

    Every app keys its committed lock per board inside one ``nsx.lock``.
    Returns the normalized board name for *board* (or the app's default
    target when *board* is unspecified), or ``None`` only when the
    manifest declares no resolvable board.
    """

    app_cfg = AppConfig.from_mapping(nsx_cfg)
    key = board or app_cfg.default_board()
    return normalize_board(key) if key else None


def _board_key_for_app(app_dir: Path, board: str | None = None) -> str | None:
    """Lock board key for *app_dir*, tolerant of a missing manifest.

    Read-only callers (``nsx outdated``, SBOM, lock-staleness) may run
    against an app dir that has a lock but no readable ``nsx.yml``; in
    that case fall back to ``None`` so the lock reader resolves the sole
    target section if the lock has exactly one.
    """

    try:
        nsx_cfg = _load_app_cfg(app_dir)
    except NSXConfigError:
        return None
    return _lock_board_key(nsx_cfg, board)


def _run_cmake_configure(
    app_dir: Path,
    build_dir: Path,
    board: str,
    toolchain: str | None = None,
    probe_serial: str | None = None,
    sdk_root: Path | None = None,
) -> None:
    from .constants import DEFAULT_TOOLCHAIN, EXPERIMENTAL_TOOLCHAINS, SUPPORTED_TOOLCHAINS

    # Resolve toolchain: explicit arg > per-board target toolchain
    # (which itself falls back to the top-level ``toolchain:``) > default
    tc = toolchain
    if tc is None:
        cfg_path = app_dir / "nsx.yml"
        if cfg_path.exists():
            cfg = _read_yaml(cfg_path)
            try:
                tc = AppConfig.from_mapping(cfg).resolve_target(board).toolchain
            except NSXConfigError:
                # Board not among declared targets (e.g. an explicit
                # ``--board`` outside the manifest): fall back to the
                # top-level toolchain key.
                tc = cfg.get("toolchain")
    tc = tc or DEFAULT_TOOLCHAIN

    tc_file = SUPPORTED_TOOLCHAINS.get(tc)
    if tc_file is None:
        supported = ", ".join(sorted(SUPPORTED_TOOLCHAINS.keys()))
        raise NSXToolchainError(f"Unknown toolchain '{tc}'. Supported: {supported}")

    if tc in EXPERIMENTAL_TOOLCHAINS:
        import logging

        logging.getLogger(__name__).warning(
            "Toolchain '%s' is experimental and not fully validated for production use.", tc
        )

    toolchain_file = app_dir / "cmake" / "nsx" / "toolchains" / tc_file
    cmd = [
        "cmake",
        "-S",
        str(app_dir),
        "-B",
        str(build_dir),
        "-G",
        "Ninja",
        f"-DCMAKE_TOOLCHAIN_FILE={toolchain_file}",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DNSX_BOARD={board}",
    ]
    # Single emit site for the out-of-tree SDK escape hatch (see AGENTS.md).
    # Always set the cache entry, including an empty value, so omitting
    # ``--sdk-root`` on a later configure clears a previously cached override
    # instead of silently building against it (nsx_sdk_providers.cmake
    # treats "" as unset). The operations layer validates the path and
    # refuses it under ``--frozen`` before we get here.
    sdk_override = str(Path(sdk_root).expanduser().resolve()) if sdk_root is not None else ""
    cmd.append(f"-DNSX_AMBIQSUITE_ROOT_OVERRIDE={sdk_override}")
    # Always set the cache entry, including an empty value, so a caller can
    # return from explicit probe selection to CMake/J-Link auto-selection.
    cmd.append(f"-DNSX_JLINK_SERIAL={probe_serial or ''}")
    jlink_executable = find_segger_tool(JLINK_NAMES)
    # CMake's flash targets and Python's reset/doctor operations must use the
    # same discovery result, including an explicit not-found state that clears
    # a stale cached executable.
    cached_jlink = jlink_executable or "NSX_JLINK_EXE-NOTFOUND"
    cmd.append(f"-DNSX_JLINK_EXE:FILEPATH={cached_jlink}")
    run(cmd)


def _resolve_app_context(args: argparse.Namespace) -> tuple[Path, dict[str, Any], str, str]:
    app_dir = Path(args.app_dir).expanduser().resolve()
    nsx_cfg = _load_app_cfg(app_dir)
    app_cfg = AppConfig.from_mapping(nsx_cfg)
    app_name = app_cfg.project_name
    board = args.board or app_cfg.default_board()
    if not isinstance(board, str) or not board:
        raise NSXConfigError("Unable to determine target board from args or nsx.yml")
    board = normalize_board(board)
    return app_dir, nsx_cfg, app_name, board


def _load_app_cfg(app_dir: Path) -> dict[str, Any]:
    cfg_path = app_dir / "nsx.yml"
    if not cfg_path.exists():
        raise NSXConfigError(
            f"App config not found: {cfg_path}\n"
            "Run this command from an NSX app directory (containing nsx.yml),\n"
            "or use 'nsx create-app <app-dir>' to create a new app."
        )
    # Route every nsx.yml read through the typed loader so that
    # structural problems surface as ``NSXConfigError(field=...)``
    # rather than opaque ``KeyError`` / ``AttributeError`` failures
    # deep inside the operations layer.
    project = NsxProject.from_yaml(cfg_path)
    cfg = project.raw
    _check_nsx_version_compatibility(cfg, cfg_path)
    _normalize_module_source(cfg)
    return cfg


def load_project_config(path: Path) -> NsxProject:
    """Public, typed loader for an app ``nsx.yml`` file.

    Returns an :class:`~neuralspotx.models.NsxProject` instance with all
    structural validation already applied. Errors raise
    :class:`NSXConfigError` whose ``.field`` names the offending YAML
    key path.

    Module-source normalisation (``source: { path: ... }`` → registry
    overrides) is applied to the underlying mapping in place so the
    legacy operations layer continues to see the same shape it always
    did. Use :meth:`NsxProject.to_yaml` for round-trip writes.
    """

    project = NsxProject.from_yaml(path)
    _check_nsx_version_compatibility(project.raw, project.path)
    _normalize_module_source(project.raw)
    # ``_normalize_module_source`` mutates ``raw`` (specifically the
    # ``module_registry`` block) in place, so the typed view computed
    # by ``from_yaml`` is now stale w.r.t. ``raw``. Rebuild it from
    # the normalized mapping to keep ``.modules`` / ``.module_registry``
    # in sync with ``.raw``.
    return NsxProject.from_mapping(project.raw, path=project.path)


def _normalize_module_source(cfg: dict[str, Any]) -> None:
    """Expand the user-facing ``source:`` field on each module entry.

    The mapping is:

      * ``source: { path: <p> }``  ->  sets ``local: true`` on the module
        entry AND injects ``module_registry.modules.<name>.local_path = <p>``
        so the existing local-path resolver picks it up unchanged.
      * ``source: { vendored: true }``  ->  left as-is; recognised by the
        lock/sync layer directly.

    Mutates *cfg* in place. The on-disk nsx.yml is not rewritten.
    """

    modules = cfg.get("modules")
    if not isinstance(modules, list):
        return

    overrides = cfg.setdefault("module_registry", {})
    if not isinstance(overrides, dict):
        return
    proj_overrides = overrides.setdefault("projects", {})
    mod_overrides = overrides.setdefault("modules", {})
    if not isinstance(mod_overrides, dict) or not isinstance(proj_overrides, dict):
        return

    app_cfg = AppConfig.from_mapping(cfg)
    for item, module in zip(modules, app_cfg.modules, strict=True):
        if not isinstance(item, dict):
            continue
        path = module.source.path
        if path:
            item["local"] = True
            entry = mod_overrides.setdefault(module.name, {})
            if isinstance(entry, dict):
                entry.setdefault("local_path", path)
                # Provide minimal registry fields so downstream
                # registry_entry_for_module() succeeds without a separate
                # `nsx module register` step.
                entry.setdefault("project", module.name)
                entry.setdefault("revision", "local")
                metadata_default = str(Path(path).expanduser() / "nsx-module.yaml")
                entry.setdefault("metadata", metadata_default)
            proj_overrides.setdefault(module.name, {"local_path": path})


def _save_app_cfg(app_dir: Path, cfg: dict[str, Any]) -> None:
    _write_yaml(app_dir / "nsx.yml", cfg)
