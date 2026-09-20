This is the standard way to install a supported first-class module into an app. The module
is appended to the app's single `modules:` list, its direct dependencies; the resolved
closure is recomputed into `nsx.lock`. For built-in modules NSX uses the registry's default
upstream repo and revision unless the app overrides that source.

```bash
cd <app-dir>
nsx module add nsx-uart
```

`--board` scopes the dependency to specific boards instead of all of `targets.supported`.
Repeat the flag for multiple boards; each must be a subset of the app's supported targets.
It writes a `boards:` filter on the entry:

```yaml
- name: nsx-pdm
  boards: [apollo510_evb]
```

`--path` adds the module as a linked dependency sourced from an external directory. The
on-disk copy under `modules/<name>/` is mirrored from that path on every `nsx sync`, and
the entry is written as `source: { path: ... }`.

`--vendored` scaffolds a custom module that lives inside this app's git repository and is
never touched by `nsx sync`, which suits AOT-generated modules, in-house drivers, or any
code that needs to be source-controlled with the app. It creates `modules/<name>/` with a
minimal `nsx-module.yaml` and `CMakeLists.txt`, appends `source: { vendored: true }` to
`nsx.yml`, regenerates `modules/.gitignore` so the directory is not ignored, and refreshes
`nsx.lock` so the module's content hash is recorded. Edit the scaffolded `CMakeLists.txt`
to add your sources, then re-run `nsx lock`.

`--local` marks the module as a local mirror, so the on-disk copy under `modules/<name>/`
is regenerated from an external source path on every sync. That path comes from either the
`source: { path: <p> }` shorthand on the module entry or from
`module_registry.modules.<name>.local_path`.
