# `nsx create-app` and `nsx new`

Creates a new NSX app from the external app template.

`nsx new` is an alias for `nsx create-app`.

## Syntax

```text
nsx create-app [--board BOARD] [--soc SOC] [--force]
               [--no-bootstrap]
               app_dir
```

## Main Arguments

- `app_dir`: app directory to create
- `--board`: target board package suffix
- `--soc`: target SoC package suffix (default inferred from board)
- `--force`: allow writing into a non-empty app directory
- `--no-bootstrap`: create the app without vendoring starter modules

## Example

```bash
nsx create-app hello_ap510 --board apollo510_evb
```

## Notes

- `--soc` is normally inferred from `--board`
- by default NSX bootstraps the starter module set for the selected board
- `--no-bootstrap` creates the app shell without vendoring any starter modules
