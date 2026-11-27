"""Software Bill of Materials (SBOM) generation for NSX apps.

Reads ``nsx.lock`` and emits a single-document SBOM in either
SPDX 2.3 (default) or CycloneDX 1.5 JSON. Package provenance comes
from the lock receipt. Optional path-scoped license declarations come
from materialized sources that match the receipt.
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid
from pathlib import Path
from typing import Any, Final, Literal, TypeGuard

from .._errors import NSXConfigError
from ..constants import normalize_board
from ..nsx_lock import LockKind, NsxLock, lock_path, read_lock_file
from ..project_config import _board_key_for_app
from ._sbom_licenses import locked_module_licenses

SBOMFormat = Literal["spdx", "cyclonedx"]

_SUPPORTED_FORMATS: Final[frozenset[str]] = frozenset({"spdx", "cyclonedx"})


def _is_sbom_format(value: str) -> TypeGuard[SBOMFormat]:
    return value in _SUPPORTED_FORMATS


def coerce_sbom_format(value: str) -> SBOMFormat:
    """Narrow a user-supplied format string to :data:`SBOMFormat`.

    Raises ``NSXConfigError`` (``field="format"``) for anything else.
    """

    if not _is_sbom_format(value):
        raise NSXConfigError(
            f"Unsupported SBOM format {value!r}. Supported: {sorted(_SUPPORTED_FORMATS)}.",
            field="format",
        )
    return value


_SPDX_NOASSERTION: Final[str] = "NOASSERTION"


def _select_locked_board(app_dir: Path, board: str | None) -> tuple[str, NsxLock]:
    receipt = read_lock_file(app_dir)
    if receipt is None:
        raise NSXConfigError(f"{lock_path(app_dir)} not found. Run `nsx lock` first.")
    if not receipt.targets:
        raise NSXConfigError("nsx.lock has no locked boards. Run `nsx lock` first.")

    key = normalize_board(board) if board is not None else _board_key_for_app(app_dir)
    if key is None and len(receipt.targets) == 1:
        return next(iter(receipt.targets.items()))
    if key is not None and key in receipt.targets:
        return key, receipt.targets[key]

    available = ", ".join(sorted(receipt.targets))
    if key is None:
        raise NSXConfigError(
            f"Select a board with --board or board=. Locked boards: {available}.", field="board"
        )
    raise NSXConfigError(
        f"Board {key!r} is missing from nsx.lock. Locked boards: {available}.", field="board"
    )


def generate_sbom_impl(
    app_dir: Path, *, format: SBOMFormat = "spdx", board: str | None = None
) -> str:
    """Serialize one board's locked inputs as SPDX or CycloneDX JSON."""
    key, lock = _select_locked_board(app_dir, board)
    if format == "spdx":
        doc = _build_spdx_document(app_dir, lock, key)
    else:
        doc = _build_cyclonedx_document(app_dir, lock, key)

    return json.dumps(doc, indent=2, sort_keys=False)


# ---------------------------------------------------------------------------
# SPDX 2.3 JSON
# ---------------------------------------------------------------------------


def _build_spdx_document(app_dir: Path, lock: NsxLock, board: str) -> dict[str, Any]:
    """Build a minimal valid SPDX 2.3 JSON document from *lock*.

    The schema is intentionally a faithful subset — the required
    top-level keys (``spdxVersion``, ``dataLicense``, ``SPDXID``,
    ``name``, ``documentNamespace``, ``creationInfo``, ``packages``)
    plus per-package metadata sufficient to identify each vendored
    module by upstream URL + commit + content hash.
    """

    app_name = app_dir.name or "nsx-app"
    timestamp = _utc_now()

    packages: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    # Root document package describes the app itself.
    root_spdxid = "SPDXRef-Package-App"
    packages.append({
        "SPDXID": root_spdxid,
        "name": app_name,
        "downloadLocation": _SPDX_NOASSERTION,
        "filesAnalyzed": False,
        "licenseConcluded": _SPDX_NOASSERTION,
        "licenseDeclared": _SPDX_NOASSERTION,
        "copyrightText": _SPDX_NOASSERTION,
    })
    relationships.append({
        "spdxElementId": "SPDXRef-DOCUMENT",
        "relationshipType": "DESCRIBES",
        "relatedSpdxElement": root_spdxid,
    })

    licenses = locked_module_licenses(app_dir, lock)
    for name, entry in sorted(lock.modules.items()):
        spdxid = f"SPDXRef-Package-{_spdxid_safe(name)}"
        download_location = entry.url or _SPDX_NOASSERTION
        if entry.kind in (LockKind.GIT, LockKind.UNRESOLVED) and entry.url and entry.commit:
            # Avoid ``git+git+https://...`` if the registry URL already
            # carries an explicit ``git+`` VCS prefix.
            base_url = entry.url
            if not base_url.startswith("git+"):
                base_url = f"git+{base_url}"
            download_location = f"{base_url}@{entry.commit}"

        pkg: dict[str, Any] = {
            "SPDXID": spdxid,
            "name": name,
            "downloadLocation": download_location,
            "filesAnalyzed": False,
            "licenseConcluded": _SPDX_NOASSERTION,
            "licenseDeclared": _SPDX_NOASSERTION,
            "copyrightText": _SPDX_NOASSERTION,
        }
        if entry.commit:
            pkg["versionInfo"] = entry.commit
        elif entry.tool_version:
            pkg["versionInfo"] = entry.tool_version

        checksums = list(_spdx_checksums_for_entry(entry.content_hash))
        if checksums:
            pkg["checksums"] = checksums

        annotations = [f"kind={entry.kind}"]
        if entry.project:
            annotations.append(f"project={entry.project}")
        if entry.constraint:
            annotations.append(f"constraint={entry.constraint}")
        if entry.tag:
            annotations.append(f"tag={entry.tag}")
        if entry.vendored_at:
            annotations.append(f"vendored_at={entry.vendored_at}")
        pkg["comment"] = "; ".join(annotations)

        if scopes := licenses.get(name):
            pkg["licenseComments"] = "\n".join(
                f"{path}: {expression or _SPDX_NOASSERTION}"
                for path, expression in sorted(scopes.items())
            )

        packages.append(pkg)
        relationships.append({
            "spdxElementId": root_spdxid,
            "relationshipType": "DEPENDS_ON",
            "relatedSpdxElement": spdxid,
        })

    namespace = (
        f"https://github.com/AmbiqAI/neuralspotx/sbom/{_document_uuid(app_name, board, timestamp)}"
    )

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{app_name}-sbom",
        "documentNamespace": namespace,
        "comment": f"nsx:board={board}",
        "creationInfo": {
            "created": timestamp,
            "creators": [
                f"Tool: neuralspotx {lock.nsx_tool_version or 'unknown'}",
            ],
        },
        "packages": packages,
        "relationships": relationships,
    }


def _spdx_checksums_for_entry(content_hash: str):
    """Yield SPDX ``checksums`` entries for an ``sha256:<hex>`` content hash."""

    if not content_hash:
        return
    # NSX always uses ``sha256:<hex>``; tolerate a missing prefix.
    algo, _, hex_value = content_hash.partition(":")
    if not hex_value:
        algo, hex_value = "sha256", algo
    yield {
        "algorithm": algo.upper(),
        "checksumValue": hex_value,
    }


def _spdxid_safe(name: str) -> str:
    """Replace SPDXID-illegal characters with ``-`` (allowed: A-Z a-z 0-9 . -)."""

    return "".join(ch if (ch.isalnum() or ch in "-.") else "-" for ch in name)


# ---------------------------------------------------------------------------
# CycloneDX 1.5 JSON
# ---------------------------------------------------------------------------


def _build_cyclonedx_document(app_dir: Path, lock: NsxLock, board: str) -> dict[str, Any]:
    """Build a minimal valid CycloneDX 1.5 JSON document from *lock*."""

    app_name = app_dir.name or "nsx-app"
    timestamp = _utc_now()

    components: list[dict[str, Any]] = []
    licenses = locked_module_licenses(app_dir, lock)
    for name, entry in sorted(lock.modules.items()):
        comp: dict[str, Any] = {
            "type": "library",
            "bom-ref": f"nsx-module:{name}",
            "name": name,
        }
        version = entry.commit or entry.tool_version
        if version:
            comp["version"] = version
        if entry.url:
            comp["purl"] = _purl_for_entry(name, entry)
            comp["externalReferences"] = [
                {"type": "vcs", "url": entry.url},
            ]
        hashes = list(_cyclonedx_hashes_for_entry(entry.content_hash))
        if hashes:
            comp["hashes"] = hashes

        properties = [{"name": "nsx:kind", "value": str(entry.kind)}]
        if entry.project:
            properties.append({"name": "nsx:project", "value": entry.project})
        if entry.constraint:
            properties.append({"name": "nsx:constraint", "value": entry.constraint})
        if entry.tag:
            properties.append({"name": "nsx:tag", "value": entry.tag})
        if entry.vendored_at:
            properties.append({"name": "nsx:vendored_at", "value": entry.vendored_at})
        properties.extend(
            {"name": f"nsx:license:{path}", "value": expression or _SPDX_NOASSERTION}
            for path, expression in sorted(licenses.get(name, {}).items())
        )
        comp["properties"] = properties

        components.append(comp)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{_document_uuid(app_name, board, timestamp)}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "properties": [{"name": "nsx:board", "value": board}],
            "tools": [
                {
                    "vendor": "AmbiqAI",
                    "name": "neuralspotx",
                    "version": lock.nsx_tool_version or "unknown",
                }
            ],
            "component": {
                "type": "application",
                "bom-ref": f"nsx-app:{app_name}",
                "name": app_name,
            },
        },
        "components": components,
    }


def _cyclonedx_hashes_for_entry(content_hash: str):
    """Yield CycloneDX ``hashes`` entries for an ``sha256:<hex>`` content hash."""

    if not content_hash:
        return
    algo, _, hex_value = content_hash.partition(":")
    if not hex_value:
        algo, hex_value = "sha256", algo
    yield {
        "alg": "SHA-256" if algo.lower() == "sha256" else algo.upper(),
        "content": hex_value,
    }


def _purl_for_entry(name: str, entry) -> str:
    """Build a best-effort Package URL (purl) for a lock entry."""

    if entry.kind in (LockKind.GIT, LockKind.UNRESOLVED) and entry.url:
        # pkg:generic with vcs URL + commit qualifier.
        commit_q = f"?vcs_url={entry.url}"
        if entry.commit:
            commit_q += f"&commit={entry.commit}"
        return f"pkg:generic/{name}{commit_q}"
    return f"pkg:generic/{name}"


def _document_uuid(app_name: str, board: str, timestamp: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(["nsx-sbom", app_name, board, timestamp]))


def _utc_now() -> str:
    """Return the current UTC timestamp in SPDX/CycloneDX-compatible ISO 8601."""

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
