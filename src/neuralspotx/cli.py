"""NSX west-backed workspace helper and module metadata orchestrator."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from . import operations
from .constants import (
    DEFAULT_REPO_NAME as _DEFAULT_REPO_NAME,
)
from .constants import (
    DEFAULT_SOC_FOR_BOARD as _DEFAULT_SOC_FOR_BOARD,
)
from .constants import (
    DEFAULT_TOOLCHAIN as _DEFAULT_TOOLCHAIN,
)
from .constants import (
    WEST_MANIFEST_TEMPLATE as _WEST_MANIFEST_TEMPLATE,
)
from .metadata import validate_nsx_module_metadata as _validate_nsx_module_metadata
from .module_registry import (
    _module_names_from_nsx,
    _print_module_table,
)
from .module_registry import (
    _remove_vendored_module_from_app as _remove_vendored_module_from_app_impl,
)
from .project_config import (
    _default_build_dir,
    _effective_registry,
    _load_app_cfg,
    _load_registry,
    _resolve_app_context,
)
from .project_config import (
    _metadata_storage_path as _metadata_storage_path_impl,
)
from .project_config import (
    _save_app_cfg as _save_app_cfg_impl,
)
from .project_config import (
    _write_app_module_file as _write_app_module_file_impl,
)
from .subprocess_utils import format_subprocess_error

DEFAULT_SOC_FOR_BOARD = _DEFAULT_SOC_FOR_BOARD
DEFAULT_TOOLCHAIN = _DEFAULT_TOOLCHAIN
DEFAULT_REPO_NAME = _DEFAULT_REPO_NAME
WEST_MANIFEST_TEMPLATE = _WEST_MANIFEST_TEMPLATE
VERBOSE = 0
validate_nsx_module_metadata = _validate_nsx_module_metadata
_metadata_storage_path = _metadata_storage_path_impl
_remove_vendored_module_from_app = _remove_vendored_module_from_app_impl
_save_app_cfg = _save_app_cfg_impl
_write_app_module_file = _write_app_module_file_impl

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cmd_init_workspace(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace).expanduser().resolve()
    operations.init_workspace_impl(
        workspace,
        nsx_repo_url=args.nsx_repo_url,
        nsx_revision=args.nsx_revision,
        ambiqsuite_repo_url=args.ambiqsuite_repo_url,
        ambiqsuite_revision=args.ambiqsuite_revision,
        skip_update=args.skip_update,
    )


def init_workspace_impl(
    workspace: Path,
    *,
    nsx_repo_url: str | None = None,
    nsx_revision: str = "main",
    ambiqsuite_repo_url: str | None = None,
    ambiqsuite_revision: str = "main",
    skip_update: bool = False,
) -> None:
    operations.init_workspace_impl(
        workspace,
        nsx_repo_url=nsx_repo_url,
        nsx_revision=nsx_revision,
        ambiqsuite_repo_url=ambiqsuite_repo_url,
        ambiqsuite_revision=ambiqsuite_revision,
        skip_update=skip_update,
    )


def cmd_create_app(args: argparse.Namespace) -> None:
    operations.create_app_impl(
        Path(args.workspace).expanduser().resolve(),
        args.name,
        board=args.board,
        soc=args.soc,
        force=args.force,
        init_workspace=args.init_workspace,
        no_bootstrap=args.no_bootstrap,
        no_sync=args.no_sync,
    )


def create_app_impl(
    workspace: Path,
    app_name: str,
    *,
    board: str = "apollo510_evb",
    soc: str | None = None,
    force: bool = False,
    init_workspace: bool = False,
    no_bootstrap: bool = False,
    no_sync: bool = False,
) -> Path:
    return operations.create_app_impl(
        workspace,
        app_name,
        board=board,
        soc=soc,
        force=force,
        init_workspace=init_workspace,
        no_bootstrap=no_bootstrap,
        no_sync=no_sync,
    )


def cmd_sync(args: argparse.Namespace) -> None:
    operations.sync_workspace_impl(Path(args.workspace).expanduser().resolve())


def sync_workspace_impl(workspace: Path) -> None:
    operations.sync_workspace_impl(workspace)


def cmd_doctor(args: argparse.Namespace) -> None:
    operations.doctor_impl()


def doctor_impl() -> None:
    operations.doctor_impl()


def cmd_configure(args: argparse.Namespace) -> None:
    operations.configure_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
    )


def cmd_build(args: argparse.Namespace) -> None:
    operations.build_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        target=args.target,
        jobs=args.jobs,
    )


def cmd_flash(args: argparse.Namespace) -> None:
    operations.flash_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        jobs=args.jobs,
    )


def _resolve_build_context(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> tuple[Path, str, str, Path]:
    resolved_app_dir, _, _, app_name, resolved_board = _resolve_app_context(
        argparse.Namespace(app_dir=str(app_dir), board=board)
    )
    resolved_build_dir = build_dir or _default_build_dir(resolved_app_dir, resolved_board)
    return resolved_app_dir, app_name, resolved_board, resolved_build_dir


def configure_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> Path:
    return operations.configure_app_impl(app_dir, board=board, build_dir=build_dir)


def build_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    target: str | None = None,
    jobs: int = 8,
) -> Path:
    return operations.build_app_impl(
        app_dir,
        board=board,
        build_dir=build_dir,
        target=target,
        jobs=jobs,
    )


def flash_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    jobs: int = 8,
) -> Path:
    return operations.flash_app_impl(
        app_dir,
        board=board,
        build_dir=build_dir,
        jobs=jobs,
    )


def cmd_view(args: argparse.Namespace) -> None:
    operations.view_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
    )


def view_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> Path:
    return operations.view_app_impl(app_dir, board=board, build_dir=build_dir)


def cmd_clean(args: argparse.Namespace) -> None:
    operations.clean_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        full=args.full,
    )


def clean_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    full: bool = False,
) -> Path:
    return operations.clean_app_impl(app_dir, board=board, build_dir=build_dir, full=full)


def cmd_module_list(args: argparse.Namespace) -> None:
    app_dir = Path(args.app_dir).expanduser().resolve()
    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(_load_registry(), nsx_cfg)
    enabled = set(_module_names_from_nsx(nsx_cfg))
    _print_module_table(registry, enabled)


def cmd_module_add(args: argparse.Namespace) -> None:
    operations.add_module_impl(
        Path(args.app_dir).expanduser().resolve(),
        args.module,
        dry_run=args.dry_run,
        no_sync=args.no_sync,
    )


def add_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> list[str]:
    return operations.add_module_impl(app_dir, module_name, dry_run=dry_run, no_sync=no_sync)


def cmd_module_remove(args: argparse.Namespace) -> None:
    operations.remove_module_impl(
        Path(args.app_dir).expanduser().resolve(),
        args.module,
        dry_run=args.dry_run,
        no_sync=args.no_sync,
    )


def remove_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> tuple[list[str], list[str]]:
    return operations.remove_module_impl(app_dir, module_name, dry_run=dry_run, no_sync=no_sync)


def cmd_module_update(args: argparse.Namespace) -> None:
    operations.update_modules_impl(
        Path(args.app_dir).expanduser().resolve(),
        module_name=args.module,
        dry_run=args.dry_run,
        no_sync=args.no_sync,
    )


def update_modules_impl(
    app_dir: Path,
    *,
    module_name: str | None = None,
    dry_run: bool = False,
    no_sync: bool = False,
) -> list[str]:
    return operations.update_modules_impl(
        app_dir,
        module_name=module_name,
        dry_run=dry_run,
        no_sync=no_sync,
    )


def cmd_module_register(args: argparse.Namespace) -> None:
    operations.register_module_impl(
        Path(args.app_dir).expanduser().resolve(),
        args.module,
        metadata=Path(args.metadata).expanduser(),
        project=args.project,
        project_url=args.project_url,
        project_revision=args.project_revision,
        project_path=args.project_path,
        project_local_path=Path(args.project_local_path).expanduser().resolve()
        if args.project_local_path
        else None,
        override=args.override,
        dry_run=args.dry_run,
        no_sync=args.no_sync,
    )


def register_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    metadata: Path,
    project: str,
    project_url: str | None = None,
    project_revision: str | None = None,
    project_path: str | None = None,
    project_local_path: Path | None = None,
    override: bool = False,
    dry_run: bool = False,
    no_sync: bool = False,
) -> Path:
    return operations.register_module_impl(
        app_dir,
        module_name,
        metadata=metadata,
        project=project,
        project_url=project_url,
        project_revision=project_revision,
        project_path=project_path,
        project_local_path=project_local_path,
        override=override,
        dry_run=dry_run,
        no_sync=no_sync,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NSX workspace-first helper for creating and building bare-metal Ambiq apps"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase CLI verbosity. Repeat for more detail.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-workspace", help="Create west manifest + init/update workspace")
    p_init.add_argument("workspace", help="Workspace directory to initialize")
    p_init.add_argument("--nsx-repo-url", default=None, help="NSX repo URL (default: packaged registry upstream URL)")
    p_init.add_argument("--nsx-revision", default="main", help="NSX revision/branch/tag")
    p_init.add_argument("--ambiqsuite-repo-url", default=None, help="Optional AmbiqSuite repo URL")
    p_init.add_argument("--ambiqsuite-revision", default="main", help="Optional AmbiqSuite revision")
    p_init.add_argument("--skip-update", action="store_true", help="Initialize manifest but skip west update")
    p_init.set_defaults(func=cmd_init_workspace)

    p_new = sub.add_parser("create-app", help="Create a new app in an initialized NSX workspace")
    p_new.add_argument("workspace", help="Workspace root")
    p_new.add_argument("name", help="Application name")
    p_new.add_argument("--board", default="apollo510_evb", help="Target board package suffix")
    p_new.add_argument("--soc", default=None, help="Target SoC package suffix (default inferred from board)")
    p_new.add_argument("--force", action="store_true", help="Allow writing into a non-empty app directory")
    p_new.add_argument(
        "--init-workspace",
        action="store_true",
        help="Initialize the workspace first if it has not been set up yet",
    )
    p_new.add_argument("--no-bootstrap", action="store_true", help="Create the app without vendoring starter modules")
    p_new.add_argument("--no-sync", action="store_true", help="Skip west update for built-in module projects during app creation")
    p_new.set_defaults(func=cmd_create_app)

    p_new_alias = sub.add_parser("new", help="Alias for create-app")
    p_new_alias.add_argument("workspace", help="Workspace root")
    p_new_alias.add_argument("name", help="Application name")
    p_new_alias.add_argument("--board", default="apollo510_evb", help="Target board package suffix")
    p_new_alias.add_argument("--soc", default=None, help="Target SoC package suffix (default inferred from board)")
    p_new_alias.add_argument("--force", action="store_true", help="Allow writing into a non-empty app directory")
    p_new_alias.add_argument(
        "--init-workspace",
        action="store_true",
        help="Initialize the workspace first if it has not been set up yet",
    )
    p_new_alias.add_argument("--no-bootstrap", action="store_true", help="Create the app without vendoring starter modules")
    p_new_alias.add_argument("--no-sync", action="store_true", help="Skip west update for built-in module projects during app creation")
    p_new_alias.set_defaults(func=cmd_create_app)

    p_sync = sub.add_parser("sync", help="Run west update in an existing workspace")
    p_sync.add_argument("workspace", help="Workspace root")
    p_sync.set_defaults(func=cmd_sync)

    p_doctor = sub.add_parser("doctor", help="Check the local NSX toolchain environment")
    p_doctor.set_defaults(func=cmd_doctor)

    p_configure = sub.add_parser("configure", help="Configure a generated NSX app with CMake")
    p_configure.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_configure.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_configure.add_argument("--build-dir", default=None, help="Build directory override")
    p_configure.set_defaults(func=cmd_configure)

    p_build = sub.add_parser("build", help="Build a generated NSX app")
    p_build.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_build.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_build.add_argument("--build-dir", default=None, help="Build directory override")
    p_build.add_argument("--target", default=None, help="Optional explicit build target")
    p_build.add_argument("--jobs", type=int, default=8, help="Parallel build jobs")
    p_build.set_defaults(func=cmd_build)

    p_flash = sub.add_parser("flash", help="Build and flash a generated NSX app")
    p_flash.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_flash.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_flash.add_argument("--build-dir", default=None, help="Build directory override")
    p_flash.add_argument("--jobs", type=int, default=8, help="Parallel build jobs")
    p_flash.set_defaults(func=cmd_flash)

    p_view = sub.add_parser("view", help="Open the SEGGER SWO viewer for a generated NSX app")
    p_view.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_view.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_view.add_argument("--build-dir", default=None, help="Build directory override")
    p_view.set_defaults(func=cmd_view)

    p_clean = sub.add_parser("clean", help="Clean a generated NSX app build directory")
    p_clean.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_clean.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_clean.add_argument("--build-dir", default=None, help="Build directory override")
    p_clean.add_argument(
        "--full",
        action="store_true",
        help="Remove the full build directory instead of only running the build-system clean target",
    )
    p_clean.set_defaults(func=cmd_clean)

    p_mod = sub.add_parser("module", help="Manage app-local NSX modules")
    mod_sub = p_mod.add_subparsers(dest="module_command", required=True)

    p_mod_list = mod_sub.add_parser("list", help="List available modules and mark enabled ones")
    p_mod_list.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_list.set_defaults(func=cmd_module_list)

    p_mod_add = mod_sub.add_parser("add", help="Enable a module for an app")
    p_mod_add.add_argument("module", help="Module name to enable")
    p_mod_add.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_add.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_add.add_argument("--no-sync", action="store_true", help="Skip west update after manifest changes")
    p_mod_add.set_defaults(func=cmd_module_add)

    p_mod_remove = mod_sub.add_parser("remove", help="Disable a module for an app")
    p_mod_remove.add_argument("module", help="Module name to remove")
    p_mod_remove.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_remove.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_remove.add_argument("--no-sync", action="store_true", help="Skip west update after manifest changes")
    p_mod_remove.set_defaults(func=cmd_module_remove)

    p_mod_update = mod_sub.add_parser("update", help="Refresh enabled modules to current registry revisions")
    p_mod_update.add_argument("module", nargs="?", default=None, help="Optional single module to refresh")
    p_mod_update.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_update.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_update.add_argument("--no-sync", action="store_true", help="Skip west update after manifest changes")
    p_mod_update.set_defaults(func=cmd_module_update)

    p_mod_register = mod_sub.add_parser("register", help="Register an external module for a single app")
    p_mod_register.add_argument("module", help="Module name")
    p_mod_register.add_argument("--metadata", required=True, help="Path to nsx-module.yaml")
    p_mod_register.add_argument("--project", required=True, help="Project/repo key")
    p_mod_register.add_argument("--project-url", default=None, help="west project URL")
    p_mod_register.add_argument("--project-revision", default=None, help="west project revision")
    p_mod_register.add_argument("--project-path", default=None, help="west project path")
    p_mod_register.add_argument("--project-local-path", default=None, help="Local filesystem module path")
    p_mod_register.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_register.add_argument("--override", action="store_true", help="Override existing module entry")
    p_mod_register.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_register.add_argument("--no-sync", action="store_true", help="Skip west update after manifest changes")
    p_mod_register.set_defaults(func=cmd_module_register)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    global VERBOSE
    VERBOSE = args.verbose
    operations.set_verbosity(args.verbose)
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        if VERBOSE > 0:
            raise
        raise SystemExit(format_subprocess_error(exc, context="Command")) from None
    return 0
