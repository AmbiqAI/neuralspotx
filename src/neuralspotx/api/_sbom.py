"""SBOM generation."""

from __future__ import annotations

from pathlib import Path

from .. import operations

PathLike = str | Path


def generate_sbom(
    app_dir: PathLike,
    *,
    format: str = "spdx",
) -> str:
    """Generate a Software Bill of Materials for the app at *app_dir*.

    Reads ``nsx.lock`` and emits a single JSON document describing
    every vendored module by upstream URL, commit SHA, and
    ``content_hash``. The returned string is ready to write to disk
    or pipe into another SBOM tool.

    Args:
        app_dir: App root containing ``nsx.lock``.
        format: ``"spdx"`` for SPDX 2.3 JSON (default) or
            ``"cyclonedx"`` for CycloneDX 1.5 JSON.

    Raises:
        NSXConfigError: ``nsx.lock`` is missing, or *format* is not
            one of ``{"spdx", "cyclonedx"}``.
    """

    return operations.generate_sbom_impl(
        Path(app_dir).expanduser().resolve(),
        format=format,  # type: ignore[arg-type]
    )
