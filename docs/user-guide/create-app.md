# Create an App

This page focuses on `nsx create-app` as the normal entry point for new work.

## Task

Generate a new app with an initial board target.

## Command

```bash
nsx create-app <app-dir> --board <board>
```

Example:

```bash
nsx create-app hello_ap510 --board apollo510_evb
```

## Templates

`--template` selects the app scaffold flavor:

| Template | Contents |
| --- | --- |
| `default` | Minimal hello-world app (SWO printf loop). |
| `npu-tflm` | TFLite Micro inference on the Ethos-U85 NPU: seeds `nsx-helia-rt` + `nsx-npu`, enables heliaRT's ethos-u dispatch, and ships a Vela model harness plus a `tools/tflite_to_header.py` converter. |

Example (atomiq110 with Ethos-U85):

```bash
nsx create-app pd_npu --board atomiq110_fpga_turbo --template npu-tflm
```

The generated `README.md` inside the app documents the offline Vela
compilation step (`vela --accelerator-config ethos-u85-256`) and how to embed
the compiled model.

## What Happens

NSX:

1. creates the app directory
2. writes `nsx.yml`
3. writes the top-level `CMakeLists.txt`
4. copies packaged `cmake/nsx/` support
5. resolves the initial module closure for the selected board
6. vendors modules and board files into the app

The selected board is the app's initial active target. The app model also
supports an explicit `targets.default` and `targets.supported` set; lifecycle
commands select one declared board at a time with `--board`.

## Result

You get a standalone app at:

```text
<app-dir>
```

If you are working from a source checkout, activate the `uv` environment first
and then run the same `nsx ...` command.

See **App Layout** for the resulting structure.
