`--soc` is normally inferred from `--board`. By default NSX bootstraps the starter module
set for the selected board; `--no-bootstrap` creates the app shell without vendoring any
starter modules.

The `--template` choices scaffold different apps:

- `default` is a minimal hello-world app built around an SWO printf loop.
- `npu-tflm` runs TFLite Micro inference on the Ethos-U85 NPU with a Vela model harness
  and heliaRT ethos-u dispatch. It seeds `nsx-helia-rt` and `nsx-npu` as direct
  dependencies and only accepts NPU boards (SoC `atomiq110`).

A template that targets specific SoCs is refused for other boards before any files are
written or modules fetched. Use `--template default` or an NPU board.

```bash
nsx create-app hello_ap510 --board apollo510_evb
nsx create-app npu_demo --board atomiq110_fpga_turbo --template npu-tflm
```
