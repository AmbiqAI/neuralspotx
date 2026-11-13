"""Read-only dependency checks at NSX configure/build boundaries."""

from pathlib import Path

from .._errors import NSXModuleError
from ..models import AppConfig
from ..module_registry import expand_profile_seeds
from ..module_registry._requirements import validate_materialized_requirements
from ..nsx_lock import read_lock
from ..project_config import _board_key_for_app, _effective_registry, _load_app_cfg, _load_registry
from ._lock import _apply_active_target


def validate_app_requirements(app_dir: Path, board: str) -> None:
    """Check current metadata against the active lock without fetching or modifying it."""
    lock = read_lock(app_dir, _board_key_for_app(app_dir, board))
    if lock is None:
        raise NSXModuleError("nsx.lock is missing. Run `nsx lock` and `nsx sync` before building.")
    cfg = _load_app_cfg(app_dir)
    app = AppConfig.from_mapping(cfg)
    if app.is_multi_target():
        cfg = _apply_active_target(cfg, app.resolve_target(board))
    base = _load_registry()
    cfg = expand_profile_seeds(cfg, base, app_dir=app_dir)
    registry = _effective_registry(base, cfg, app_dir=app_dir)
    validate_materialized_requirements(
        list(lock.modules), app_dir=app_dir, nsx_cfg=cfg, registry=registry
    )
    from ..module_registry._composition import verify_board_composition

    verify_board_composition(lock.board_composition, app_dir, cfg, registry, list(lock.modules))
