# ExecuTorch Cortex-M CMSIS-NN validation

This application validates the complete ExecuTorch Cortex-M path on an Apollo510 EVB. It replaces the former portable `aten::add.out` smoke test.

The test model is a deterministic `Conv2d(2, 4, 3, bias=False)` with float32 external input and output. Export inserts int8 quantization around the convolution and lowers the graph to exactly these operators:

- `cortex_m::quantize_per_tensor.out`
- `cortex_m::quantized_conv2d.out`
- `cortex_m::dequantize_per_tensor.out`

The middle operator calls upstream Arm CMSIS-NN's `arm_convolve_wrapper_s8`. ExecuTorch portable operators are disabled. The runtime links the standard `arm-cmsis-nn` NSX module, not Ambiq's API-modified `ns-cmsis-nn` Helia implementation.

## What is validated

The export script fails unless the transformed graph contains exactly the three Cortex-M operators above. It writes the `.pte`, physical channels-last input bytes, the host quantized reference output, and a tolerance derived from the output quantization scale.

On target, the application compares all 36 float output elements against that reference. Success is printed as:

```text
EXECUTORCH_CMSIS_NN_OK ...
```

The final link also fails unless the ELF contains both the ExecuTorch Cortex-M `quantized_conv2d_out` implementation and CMSIS-NN's `arm_convolve_wrapper_s8`. This prevents a portable fallback from accidentally passing the numerical test.

For debugger automation, these RAM symbols are exported:

- `executorch_cmsis_nn_status`: `0` while pending, `1` on success, high bit set on failure
- `executorch_cmsis_nn_error`: ExecuTorch error code
- `executorch_cmsis_nn_max_error_micro`: maximum absolute error multiplied by one million

## Export the model

The exporter requires the ExecuTorch v1.3.0 source's pinned PyTorch 2.12 and torchao environment, plus the Cortex-M requirements. Run it with the ExecuTorch source package visible on `PYTHONPATH`:

```bash
PYTHONPATH=/path/to/executorch/src \
python examples/executorch_cmsis_nn/model/export_model.py
```

PyTorch 2.12 emits an unused `_guards_fn` module in this environment. The exporter removes it only after proving it has no users, because the current ExecuTorch export-pass interpreter rejects `call_module` nodes.

Input and reference arrays are emitted in physical NHWC order. The logical tensor shapes remain PyTorch NCHW, but the Cortex-M convolution requires channels-last storage.

## Build through NSX

This is currently a two-checkout development example: `nsx.yml` points to an adjacent `nsx-executorch` checkout containing the integration changes. A standalone NeuralSPOT-X checkout cannot resolve that local override until nsx-executorch is committed and published in the registry.

From the NeuralSPOT-X repository root:

```bash
uv run nsx lock --app examples/executorch_cmsis_nn
uv run nsx sync --app examples/executorch_cmsis_nn
uv run nsx configure examples/executorch_cmsis_nn \
  --board apollo510_evb \
  --build-dir examples/executorch_cmsis_nn/build/cmsis_nn
uv run nsx build examples/executorch_cmsis_nn \
  --board apollo510_evb \
  --build-dir examples/executorch_cmsis_nn/build/cmsis_nn
```

Configuration and compilation are offline after `nsx sync`. The app-local module closure includes upstream CMSIS-NN and CMSIS 6 through `arm-cmsis-nn`.

The successful build reports:

```text
Verified ExecuTorch Cortex-M and CMSIS-NN Conv2D symbols in .../executorch_cmsis_nn
```

## Run on Apollo510 EVB

With a SEGGER J-Link probe connected:

```bash
uv run nsx flash examples/executorch_cmsis_nn \
  --board apollo510_evb \
  --build-dir examples/executorch_cmsis_nn/build/cmsis_nn \
  --target executorch_cmsis_nn
```

Use SWO output to observe the pass/fail line, or read the three debugger status symbols above. Flashing cannot proceed when J-Link Commander reports that no probe is connected.
