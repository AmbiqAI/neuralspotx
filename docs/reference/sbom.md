# `nsx sbom`

Generates a **Software Bill of Materials** (SBOM) for an NSX app from
its `nsx.lock`. The SBOM lists every vendored module by name with its
upstream URL, locked commit SHA, and content hash, so downstream tools
(audits, vulnerability scanners, reproducibility checks) can verify
exactly what an `nsx sync` of the lock would materialise.

## Syntax

```bash
nsx sbom [--app-dir DIR] [--format spdx|cyclonedx] [--output FILE]
```

## Options

| Option | Default | Description |
|---|---|---|
| `--app-dir` | `.` | App directory containing `nsx.lock`. |
| `--format` | `spdx` | SBOM format. `spdx` emits SPDX 2.3 JSON; `cyclonedx` emits CycloneDX 1.5 JSON. |
| `--output`, `-o` | *(stdout)* | Write the SBOM to a file instead of stdout. |

## Examples

Print an SPDX 2.3 SBOM to stdout:

```bash
nsx sbom
```

Write a CycloneDX 1.5 SBOM to disk:

```bash
nsx sbom --format cyclonedx --output bom.json
```

## Sources

For each module in `nsx.lock`, the SBOM records:

- The upstream URL and commit SHA (for `git` / `unresolved` kinds).
- The locked `content_hash` (always; emitted as a SHA-256 checksum).
- The resolution kind, registry project key, and constraint as
  package-level annotations.

License metadata is not currently carried in the lock or in
`nsx-module.yaml`; every package is emitted with `NOASSERTION` (SPDX)
or with no `licenses` array (CycloneDX) until license fields are
added in a later release.

## Programmatic API

The same payload is available from Python:

```python
from neuralspotx import generate_sbom

doc = generate_sbom("/path/to/app", format="spdx")
```

`generate_sbom` returns the JSON document as a string. It raises
`NSXConfigError` if `nsx.lock` is missing or if `format` is not in
`{"spdx", "cyclonedx"}`.

## Related Commands

- [`nsx lock`](../user-guide/lock-and-sync.md) — produce or refresh
  `nsx.lock` (the SBOM input).
- [`nsx sync`](../user-guide/lock-and-sync.md) — materialise the
  modules described by the lock.
