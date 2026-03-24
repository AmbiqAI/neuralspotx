# `nsx sync`

Runs `west update` in an existing workspace.

## Syntax

```text
nsx sync workspace
```

## Main Arguments

- `workspace`: workspace root

## Example

```bash
cd <nsx-repo>
uv run nsx sync <workspace>
```

## Notes

- use this when you want to refresh workspace-managed source repos
