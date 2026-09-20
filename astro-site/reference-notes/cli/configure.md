`--board` must name a declared supported target. `--sdk-root` builds against an out-of-tree
AmbiqSuite root (`NSX_AMBIQSUITE_ROOT_OVERRIDE`) instead of the vendored `nsx-ambiqsuite`;
it must be a directory, it warns that `nsx.lock` and the SBOM no longer describe the
binary, and it cannot be combined with `--frozen`. Omitting it clears a previously cached
override.

```bash
cd <app-dir>
nsx configure
```

Run `nsx commands --json` for the authoritative machine-readable argument schema.
