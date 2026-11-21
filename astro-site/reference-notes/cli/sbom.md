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

A materialized tree that matches its locked hash can supply path-scoped licenses.
NSX reads the selected manifest recorded in each module’s `resolved.manifest_path`. SPDX reports
the scopes in `licenseComments` and CycloneDX uses `nsx:license:<path>` properties.
For Git modules, NSX omits declarations if the selected path passes through a directory
symlink, because the artifact hash walk skips linked directories.
Paths in both exports are relative to the recorded `vendored_at` directory.
Packaged boards and `nsx-tooling` declare BSD-3-Clause at `.`, the root of their own trees.

After upgrading from 0.9.8 or earlier, run `nsx lock` and review the changed
packaged hashes and Git pins. Run `nsx sync` to refresh the default board and
tooling before exporting again. For additional targets, `nsx configure --board <board>` runs the corresponding sync.
Keep using the original wheel to reproduce an older lock from a clean checkout.

The same payload is available from Python:

```python
from neuralspotx import generate_sbom

doc = generate_sbom("/path/to/app", format="spdx")
```

`generate_sbom` returns the JSON document as a string. It raises `NSXConfigError` if
`nsx.lock` is missing or if `format` is not `spdx` or `cyclonedx`.
