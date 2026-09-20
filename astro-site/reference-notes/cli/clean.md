`--reset` is broader than a normal or `--full` clean: it removes all `build*/` directories,
the synced `modules/` tree and `.nsx/`, restoring freshly cloned app state. Review local
module changes before combining it with `--force`, which discards modified files under
`modules/` without prompting.

```bash
cd <app-dir>
nsx clean
```

Run `nsx commands --json` for the authoritative machine-readable argument schema.

`--app-dir` names the app directory containing `nsx.yml`; when it is omitted NSX searches
upward from the current directory. The positional `app` argument overrides `--app-dir` and
is resolved under the current directory and under `examples/`.
