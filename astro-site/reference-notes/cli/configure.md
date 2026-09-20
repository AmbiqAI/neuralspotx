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

`--app-dir` names the app directory containing `nsx.yml`; when it is omitted NSX searches
upward from the current directory. The positional `app` argument overrides `--app-dir` and
is resolved under the current directory and under `examples/`.

{/* TODO(#260): link the SDK provider selection guide once it is migrated. */}
The out-of-tree SDK escape hatch is described under SDK provider selection in the guides.
