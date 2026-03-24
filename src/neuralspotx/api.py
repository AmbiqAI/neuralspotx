"""Programmatic API for the NSX workflow."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from . import cli


class NSXError(RuntimeError):
    """Raised when an NSX workflow operation fails."""


def _invoke(func: Any, **kwargs: Any) -> None:
    try:
        func(argparse.Namespace(**kwargs))
    except SystemExit as exc:
        code = exc.code
        if code in (None, 0):
            return
        raise NSXError(str(code)) from None


def init_workspace(
    workspace: str | Path,
    *,
    nsx_repo_url: str | None = None,
    nsx_revision: str = "main",
    ambiqsuite_repo_url: str | None = None,
    ambiqsuite_revision: str = "main",
    skip_update: bool = False,
) -> None:
    _invoke(
        cli.cmd_init_workspace,
        workspace=str(workspace),
        nsx_repo_url=nsx_repo_url,
        nsx_revision=nsx_revision,
        ambiqsuite_repo_url=ambiqsuite_repo_url,
        ambiqsuite_revision=ambiqsuite_revision,
        skip_update=skip_update,
    )


def create_app(
    workspace: str | Path,
    name: str,
    *,
    board: str = "apollo510_evb",
    soc: str | None = None,
    force: bool = False,
    init_workspace: bool = False,
    no_bootstrap: bool = False,
    no_sync: bool = False,
) -> None:
    _invoke(
        cli.cmd_create_app,
        workspace=str(workspace),
        name=name,
        board=board,
        soc=soc,
        force=force,
        init_workspace=init_workspace,
        no_bootstrap=no_bootstrap,
        no_sync=no_sync,
    )


def sync_workspace(workspace: str | Path) -> None:
    _invoke(cli.cmd_sync, workspace=str(workspace))


def doctor() -> None:
    _invoke(cli.cmd_doctor)


def configure_app(
    app_dir: str | Path,
    *,
    board: str | None = None,
    build_dir: str | Path | None = None,
) -> None:
    _invoke(
        cli.cmd_configure,
        app_dir=str(app_dir),
        board=board,
        build_dir=str(build_dir) if build_dir is not None else None,
    )


def build_app(
    app_dir: str | Path,
    *,
    board: str | None = None,
    build_dir: str | Path | None = None,
    target: str | None = None,
    jobs: int = 8,
) -> None:
    _invoke(
        cli.cmd_build,
        app_dir=str(app_dir),
        board=board,
        build_dir=str(build_dir) if build_dir is not None else None,
        target=target,
        jobs=jobs,
    )


def flash_app(
    app_dir: str | Path,
    *,
    board: str | None = None,
    build_dir: str | Path | None = None,
    jobs: int = 8,
) -> None:
    _invoke(
        cli.cmd_flash,
        app_dir=str(app_dir),
        board=board,
        build_dir=str(build_dir) if build_dir is not None else None,
        jobs=jobs,
    )


def view_app(
    app_dir: str | Path,
    *,
    board: str | None = None,
    build_dir: str | Path | None = None,
) -> None:
    _invoke(
        cli.cmd_view,
        app_dir=str(app_dir),
        board=board,
        build_dir=str(build_dir) if build_dir is not None else None,
    )


def clean_app(
    app_dir: str | Path,
    *,
    board: str | None = None,
    build_dir: str | Path | None = None,
    full: bool = False,
) -> None:
    _invoke(
        cli.cmd_clean,
        app_dir=str(app_dir),
        board=board,
        build_dir=str(build_dir) if build_dir is not None else None,
        full=full,
    )


def add_module(
    app_dir: str | Path,
    module: str,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> None:
    _invoke(
        cli.cmd_module_add,
        app_dir=str(app_dir),
        module=module,
        dry_run=dry_run,
        no_sync=no_sync,
    )


def remove_module(
    app_dir: str | Path,
    module: str,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> None:
    _invoke(
        cli.cmd_module_remove,
        app_dir=str(app_dir),
        module=module,
        dry_run=dry_run,
        no_sync=no_sync,
    )


def update_modules(
    app_dir: str | Path,
    *,
    module: str | None = None,
    dry_run: bool = False,
    no_sync: bool = False,
) -> None:
    _invoke(
        cli.cmd_module_update,
        app_dir=str(app_dir),
        module=module,
        dry_run=dry_run,
        no_sync=no_sync,
    )


def register_module(
    app_dir: str | Path,
    module: str,
    *,
    metadata: str | Path,
    project: str,
    project_url: str | None = None,
    project_revision: str | None = None,
    project_path: str | None = None,
    project_local_path: str | Path | None = None,
    override: bool = False,
    dry_run: bool = False,
    no_sync: bool = False,
) -> None:
    _invoke(
        cli.cmd_module_register,
        app_dir=str(app_dir),
        module=module,
        metadata=str(metadata),
        project=project,
        project_url=project_url,
        project_revision=project_revision,
        project_path=project_path,
        project_local_path=str(project_local_path) if project_local_path is not None else None,
        override=override,
        dry_run=dry_run,
        no_sync=no_sync,
    )
