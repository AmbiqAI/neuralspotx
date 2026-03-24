# `nsx create-app` and `nsx new`

Creates a new NSX app from the external app template.

`nsx new` is an alias for `nsx create-app`.

## Syntax

```text
nsx create-app [--board BOARD] [--soc SOC] [--force]
               [--init-workspace]
               [--no-bootstrap] [--no-sync]
               workspace name
```

## Main Arguments

- `workspace`: workspace root
- `name`: application name
- `--board`: target board package suffix
- `--soc`: target SoC package suffix
- `--force`: allow writing into a non-empty app directory
- `--init-workspace`: initialize the workspace first if needed
- `--no-bootstrap`: create the app without vendoring starter modules
- `--no-sync`: skip `west update` for built-in module repos during app creation

## Example

```bash
cd <nsx-repo>
uv run nsx create-app <workspace> hello_ap510 --board apollo510_evb
```

If the workspace does not exist yet:

```bash
cd <nsx-repo>
uv run nsx create-app <workspace> hello_ap510 --board apollo510_evb --init-workspace
```

## Notes

- `--soc` is normally inferred from `--board`
- `--init-workspace` keeps the workspace-first model but removes one manual step
- by default NSX bootstraps the starter module set for the selected board
- `--no-bootstrap` creates the app shell without vendoring any starter modules
