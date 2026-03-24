# `nsx init-workspace`

Creates a workspace manifest and initializes a workspace for NSX.

## Syntax

```text
nsx init-workspace [--nsx-repo-url URL] [--nsx-revision REVISION]
                   [--ambiqsuite-repo-url URL]
                   [--ambiqsuite-revision REVISION]
                   [--skip-update]
                   workspace
```

## Main Arguments

- `workspace`: workspace directory to initialize
- `--nsx-repo-url`: NSX repo URL
- `--nsx-revision`: NSX branch, tag, or revision
- `--ambiqsuite-repo-url`: optional AmbiqSuite repo URL
- `--ambiqsuite-revision`: optional AmbiqSuite revision
- `--skip-update`: initialize the manifest but skip `west update`

## Example

```bash
cd <nsx-repo>
uv run nsx init-workspace <workspace> --skip-update
```

## Notes

- this writes `manifest/west.yml`
- by default the NSX tooling repo URL comes from the packaged registry
- this is the normal first step before `create-app`
