# `nsx create-app` and `nsx new`

Creates a new NSX app from a packaged app template.

`nsx new` is an alias for `nsx create-app`.

## Syntax

```text
nsx create-app [--board BOARD] [--soc SOC] [--force]
               [--no-bootstrap] [--template {default,npu-tflm}]
               app_dir
```

## Main Arguments

- `app_dir`: app directory to create
- `--board`: target board package suffix
- `--soc`: target SoC package suffix (default inferred from board)
- `--force`: allow writing into a non-empty app directory
- `--no-bootstrap`: create the app without vendoring starter modules
- `--template`: app template to scaffold from:
    - `default`: minimal hello-world app (SWO printf loop)
    - `npu-tflm`: TFLite Micro inference on the Ethos-U85 NPU (Vela model
      harness, heliaRT ethos-u dispatch); seeds `nsx-helia-rt` and `nsx-npu`
      as direct dependencies and only accepts NPU boards (SoC `atomiq110`)

## Example

```bash
nsx create-app hello_ap510 --board apollo510_evb
nsx create-app npu_demo --board atomiq110_fpga_turbo --template npu-tflm
```

## Notes

- `--soc` is normally inferred from `--board`
- by default NSX bootstraps the starter module set for the selected board
- `--no-bootstrap` creates the app shell without vendoring any starter modules
- a template that targets specific SoCs (`npu-tflm` → `atomiq110`) is refused
  for other boards before any files are written or modules fetched; use
  `--template default` or an NPU board
