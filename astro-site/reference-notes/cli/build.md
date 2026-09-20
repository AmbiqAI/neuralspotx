`nsx build` operates on the generated app's CMake build tree. When `--app-dir` is omitted
NSX searches upward from the current directory for `nsx.yml`; the positional `app` argument
overrides that and is resolved under the current directory and `examples/`.

`--sdk-root` is an escape hatch that builds against an out-of-tree AmbiqSuite root
(`NSX_AMBIQSUITE_ROOT_OVERRIDE`). It warns that `nsx.lock` and the SBOM no longer describe
the binary, cannot be combined with `--frozen`, and forces a reconfigure when it differs
from the cached override.

```bash
cd <app-dir>
nsx build --jobs 8
```

Run `nsx commands --json` for the authoritative machine-readable argument schema.

{/* TODO(#260): link the SDK provider selection guide once it is migrated. */}
The out-of-tree SDK escape hatch is described under SDK provider selection in the guides.
