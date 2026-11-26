The SBOM is a receipt for one board’s locked inputs. It lists the modules recorded in
that section of `nsx.lock`, including their available source revisions and hashes.

```bash
# SPDX 2.3 to stdout
nsx sbom

# CycloneDX 1.5 for a specific board
nsx sbom --board apollo510b_evb --format cyclonedx --output bom.json
```

An explicit board selects a section directly from the lock, even without `nsx.yml`.
From a subdirectory, the CLI uses the nearest directory containing `nsx.yml` or
`nsx.lock`, up to the Git repository boundary.
Omit `--board` to export the configured default. If the default is unavailable and
the lock contains one board, NSX uses that board. For a lock with multiple boards
and no configured default, pass `--board`. A configured default needs its own lock section.
The SPDX document comment and the
CycloneDX metadata property `nsx:board` identify the selected board.

For each module in that section the SBOM records the upstream URL and commit SHA (for `git`
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
tooling before exporting again.
Keep using the original wheel to reproduce an older lock from a clean checkout.

The same payload is available from Python:

```python
from neuralspotx import generate_sbom

doc = generate_sbom("/path/to/app", board="apollo510b_evb", format="spdx")
```

`generate_sbom` returns the JSON document as a string. It raises `NSXConfigError` if
the board cannot be selected, `nsx.lock` is missing, or `format` is not `spdx` or `cyclonedx`.
