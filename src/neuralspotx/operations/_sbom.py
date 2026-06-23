"""Software Bill of Materials (SBOM) generation for NSX apps.

Reads ``nsx.lock`` and emits a single-document SBOM in either
SPDX 2.3 (default) or CycloneDX 1.5 JSON. Sources every field
from the lock receipt — per-module commit SHA + content hash +
registry URL — so the SBOM faithfully describes what an
``nsx sync`` of the lock would materialise.

License metadata is not currently carried in the lock or in
``nsx-module.yaml``; every package is emitted with
``NOASSERTION`` (SPDX) / no ``licenses`` array (CycloneDX) until a
later phase wires that through.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Final, Literal

from .._errors import NSXConfigError
from ..nsx_lock import LockKind, NsxLock, lock_path, read_lock
from ..project_config import _board_key_for_app

SBOMFormat = Literal["spdx", "cyclonedx"]

_SUPPORTED_FORMATS: Final[frozenset[str]] = frozenset({"spdx", "cyclonedx"})

_SPDX_NOASSERTION: Final[str] = "NOASSERTION"


def generate_sbom_impl(app_dir: Path, *, format: SBOMFormat = "spdx") -> str:
    """Return a serialized SBOM for the app at *app_dir*.

    Args:
        app_dir: App root containing ``nsx.lock``.
        format: ``"spdx"`` for SPDX 2.3 JSON (default) or
            ``"cyclonedx"`` for CycloneDX 1.5 JSON.

    Raises:
        NSXConfigError: ``nsx.lock`` is missing, or *format* is not in
            ``{"spdx", "cyclonedx"}``.

    The returned string is a complete JSON document, ready to write to
    disk or pipe into another SBOM tool.
    """

    if format not in _SUPPORTED_FORMATS:
        raise NSXConfigError(
            f"Unsupported SBOM format {format!r}. Supported: {sorted(_SUPPORTED_FORMATS)}.",
            field="format",
        )

    board_key = _board_key_for_app(app_dir)
    lock = read_lock(app_dir, board_key)
    if lock is None:
        raise NSXConfigError(f"{lock_path(app_dir)} not found. Run `nsx lock` first.")

    if format == "spdx":
        doc = _build_spdx_document(app_dir, lock)
    else:
        doc = _build_cyclonedx_document(app_dir, lock)

    return json.dumps(doc, indent=2, sort_keys=False)


# ---------------------------------------------------------------------------
# SPDX 2.3 JSON
# ---------------------------------------------------------------------------


def _build_spdx_document(app_dir: Path, lock: NsxLock) -> dict[str, Any]:
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

        packages.append(pkg)
        relationships.append({
            "spdxElementId": root_spdxid,
            "relationshipType": "DEPENDS_ON",
            "relatedSpdxElement": spdxid,
        })

    namespace = (
        "https://github.com/AmbiqAI/neuralspotx/sbom/"
        f"{app_name}-{hashlib.sha256(timestamp.encode('utf-8')).hexdigest()[:16]}"
    )

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{app_name}-sbom",
        "documentNamespace": namespace,
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


def _build_cyclonedx_document(app_dir: Path, lock: NsxLock) -> dict[str, Any]:
    """Build a minimal valid CycloneDX 1.5 JSON document from *lock*."""

    app_name = app_dir.name or "nsx-app"
    timestamp = _utc_now()

    components: list[dict[str, Any]] = []
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
        comp["properties"] = properties

        components.append(comp)

    # CycloneDX requires an RFC 4122 UUID URN; derive it deterministically
    # from app_name + timestamp via uuid5 so two identical inputs produce
    # an identical (and well-formed) serial number.
    serial_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"nsx-sbom:{app_name}:{timestamp}")
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial_uuid}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
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


def _purl_for_entry(name: str, entry) -> str:  # type: ignore[no-untyped-def]
    """Build a best-effort Package URL (purl) for a lock entry."""

    if entry.kind in (LockKind.GIT, LockKind.UNRESOLVED) and entry.url:
        # pkg:generic with vcs URL + commit qualifier.
        commit_q = f"?vcs_url={entry.url}"
        if entry.commit:
            commit_q += f"&commit={entry.commit}"
        return f"pkg:generic/{name}{commit_q}"
    return f"pkg:generic/{name}"


def _utc_now() -> str:
    """Return the current UTC timestamp in SPDX/CycloneDX-compatible ISO 8601."""

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
