"""SBOM generation."""

from __future__ import annotations

from pathlib import Path

from .. import operations

PathLike = str | Path


def generate_sbom(
    app_dir: PathLike,
    *,
    format: str = "spdx",
    board: str | None = None,
) -> str:
    """Generate a Software Bill of Materials for the app at *app_dir*.

    Reads ``nsx.lock`` and emits a single JSON document describing
    one board’s locked modules and their recorded provenance.

    Args:
        app_dir: App root containing ``nsx.lock``.
        board: Board key in the lock. Defaults to the configured board, or the
            sole locked board when the app default is unavailable.
        format: ``"spdx"`` for SPDX 2.3 JSON (default) or
            ``"cyclonedx"`` for CycloneDX 1.5 JSON.

    Raises:
        NSXConfigError: ``nsx.lock`` is missing, board selection fails, or *format* is not
            one of ``{"spdx", "cyclonedx"}``.
    """

    return operations.generate_sbom_impl(
        Path(app_dir).expanduser().resolve(),
        format=operations.coerce_sbom_format(format),
        board=board,
    )
