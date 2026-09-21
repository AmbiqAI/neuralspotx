The SBOM is generated from the app's `nsx.lock`. It lists every vendored module by name
with its upstream URL, locked commit SHA and content hash, so downstream tools (audits,
vulnerability scanners, reproducibility checks) can verify exactly what an `nsx sync` of the
lock would materialize.

```bash
# SPDX 2.3 to stdout
nsx sbom

# CycloneDX 1.5 to disk
nsx sbom --format cyclonedx --output bom.json
```

For each module in `nsx.lock` the SBOM records the upstream URL and commit SHA (for `git`
and `unresolved` kinds), the locked `content_hash` (always, as a SHA-256 checksum), and the
resolution kind, registry project key, requested constraint and matched tag as
package-level annotations. It also records the neuralspotx tool version that produced the
lock. These fields expose explicit development overrides: branch refs retain both the
requested ref and the resolved commit, while local projects are identified by their `local`
kind and exact content hash.

License metadata is not carried in the lock or in `nsx-module.yaml`, so every package is
emitted with `NOASSERTION` (SPDX) or with no `licenses` array (CycloneDX).

The same payload is available from Python:

```python
from neuralspotx import generate_sbom

doc = generate_sbom("/path/to/app", format="spdx")
```

`generate_sbom` returns the JSON document as a string. It raises `NSXConfigError` if
`nsx.lock` is missing or if `format` is not `spdx` or `cyclonedx`.
