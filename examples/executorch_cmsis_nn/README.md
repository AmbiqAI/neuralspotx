# ExecuTorch Cortex-M CMSIS-NN runner validation

This application validates the NSX ExecuTorch runner on an Apollo510 EVB. It does not create, export, quantize, or lower a model. It consumes a prebuilt ExecuTorch PTE and packages that PTE into the board firmware.

The included fixture is model/resnet8_cmsis_nn.pte, a 173 KB MLPerf Tiny-style ResNet-8 PTE for 32x32 RGB input and 10-class output. It is treated as an opaque runner input.

## Responsibility boundary

Before NSX:

1. A model owner creates a PTE using their chosen ExecuTorch export pipeline.
2. The model owner supplies the PTE, its required operator list, and its input/output contract.

Inside NSX:

1. NSX resolves the ExecuTorch, board, CMSIS-NN, and CMSIS dependencies.
2. CMake converts the supplied PTE bytes into a read-only C array stored in firmware flash. This packaging step does not modify or compile the PTE.
3. Selective code generation registers the Cortex-M operators named by NSX_EXECUTORCH_CORTEX_M_SELECT_OPS_LIST and the portable ATen fallback operators named by NSX_EXECUTORCH_PORTABLE_SELECT_OPS_LIST.
4. The linker combines the PTE, standard ExecuTorch runtime, selected portable kernels, Cortex-M operator implementations, the selected CMSIS-NN provider, and Apollo510 board support.
5. main.cc passes the embedded PTE and caller-owned memory arenas to nsx::executorch::run_once.

The nsx-executorch module uses the standard ExecuTorch lifecycle: load Program, inspect the forward method, create MemoryManager objects, load the method, set inputs, execute, and retrieve outputs.

## Supplied fixture contract

The included PTE requires:

- cortex_m::quantize_per_tensor.out
- cortex_m::quantized_conv2d.out
- cortex_m::quantized_add.out
- cortex_m::quantized_avg_pool2d.out
- cortex_m::quantized_linear.out
- cortex_m::dequantize_per_tensor.out

Those Cortex-M operators call CMSIS-NN-compatible functions including arm_convolve_wrapper_s8, arm_elementwise_add_s8, and arm_avgpool_s8. The implementation of those functions comes from the selected CMSIS-NN provider. This ResNet-8 PTE does not itself require portable operators. The example nevertheless prelinks the additional kernels found in a larger ResNet18 graph: the Cortex-M max-pool and transpose operators plus the portable aten::clamp.out and aten::addmm.out fallbacks. This validates that NSX can compose Cortex-M and portable kernels in one firmware image without enabling the entire portable operator library.

The fixture-specific input and expected output live in src/validation_data.h. A different contract can be supplied with NSX_EXECUTORCH_VALIDATION_HEADER. The runner compares all 10 output logits against that supplied reference. These values are validation data, not model-export code.

The Apollo510 hardware run on 2026-08-13 returned status 1, ExecuTorch error 0, and maximum numerical error 0.

## Select the CMSIS-NN provider

`NSX_EXECUTORCH_CMSIS_NN_PROVIDER` is a CMake cache switch with two values:

- `arm` (the default) links upstream Arm CMSIS-NN through `nsx::arm_cmsis_nn`.
- `ns` links Ambiq's optimized ns-cmsis-nn through `nsx::cmsis_nn`.

The supplied PTE, operator list, runner API, and application code do not change when the provider changes. For example, after NSX creates a build directory, select ns-cmsis-nn with:

~~~bash
uv run nsx configure examples/executorch_cmsis_nn \
  --board apollo510_evb \
  --build-dir examples/executorch_cmsis_nn/build/resnet8-ns
cmake -S examples/executorch_cmsis_nn \
  -B examples/executorch_cmsis_nn/build/resnet8-ns \
  -DNSX_EXECUTORCH_CMSIS_NN_PROVIDER=ns
~~~

For ns-cmsis-nn, the native Cortex-M lowering precomputes the fork's required per-output-channel weight sums and serializes them as constants in the PTE. The runtime adapter only points the NS CMSIS-NN context at those constants; it does not allocate or calculate them during inference. The same newly exported PTE works with either provider, but PTEs exported before this operator-schema change must be regenerated.

The post-link verifier checks the linker map, not only function names, so a build fails if the selected provider's archive was not actually linked. On 2026-08-13, both provider variants ran the included ResNet-8 on an Apollo510 EVB and returned status 1, ExecuTorch error 0, and maximum numerical error 0.

## Supply a different PTE

NSX_EXECUTORCH_PTE is a CMake FILEPATH cache variable. It defaults to:

~~~text
model/resnet8_cmsis_nn.pte
~~~

To use another PTE, provide its path through that cache setting and also set:

- NSX_EXECUTORCH_CORTEX_M_SELECT_OPS_LIST to match the PTE Cortex-M custom operators.
- NSX_EXECUTORCH_PORTABLE_SELECT_OPS_LIST, as a comma-separated list, to match any portable ATen fallback operators in the PTE; leave it empty to disable portable kernels.
- NSX_EXECUTORCH_VALIDATION_HEADER to a header that provides the input, expected output, sizes, and tolerance in the executorch_cmsis_nn_validation namespace.

Increase the caller-owned arenas in src/main.cc if the PTE metadata reports a larger planned-memory requirement. The post-link check follows the configured operator lists and verifies the corresponding Cortex-M, portable, and CMSIS-NN symbols.

The reusable nsx::executorch::run_once API itself is model-independent. The example application around it is necessarily model-aware because it owns the input and output buffers.


### MobileNetV1-0.25 hardware validation

The upstream ExecuTorch MobileNetV1-0.25 Cortex-M example was tested as an externally supplied 298,072-byte PTE with a 1x96x96x3 physical input and two outputs. Its exact selected operator set was quantize, Conv2D, depthwise Conv2D, average pool, linear, and dequantize; portable operators were disabled. The PTE reported a 138,240-byte planned arena requirement.

On the Apollo510 EVB, the runner returned status 1, ExecuTorch error 0, and maximum absolute error 0 against the upstream-generated reference output. On 2026-08-11, the same supplied PTE and reference also passed with `NSX_EXECUTORCH_CMSIS_NN_PROVIDER=ns`, exercising ns-cmsis-nn's standard, depthwise, pooling, and fully connected paths. This validates runtime execution and CMSIS-NN kernel integration. The example model uses random weights, so this is not an application-accuracy measurement.

## Build through NSX

This is currently a two-checkout development example: nsx.yml points to an adjacent nsx-executorch checkout. From the NeuralSPOT-X repository root:

~~~bash
uv run nsx lock --app examples/executorch_cmsis_nn
uv run nsx sync --app examples/executorch_cmsis_nn
uv run nsx configure examples/executorch_cmsis_nn --board apollo510_evb --build-dir examples/executorch_cmsis_nn/build/resnet8
uv run nsx build examples/executorch_cmsis_nn --board apollo510_evb --build-dir examples/executorch_cmsis_nn/build/resnet8
~~~

The successful build verifies that the final ELF contains the selected ExecuTorch Cortex-M and portable implementations plus the required CMSIS-NN functions. The additional kernels increase firmware text size but do not materially change the ResNet-8 runner arena requirements.

## Profile with heliaPROFILER

The adjacent heliaPROFILER checkout contains an ExecuTorch engine adapter and a
ready-to-run configuration for this fixture. It builds `nsx-executorch` with
ExecuTorch EventTracer hooks, reports one PMU row per kernel/delegate
instruction, and separately reports clean `Method::execute()` total cycles.

From the helia-profiler repository root:

~~~bash
uv run hpx profile \
  --config configs/executorch/resnet8_cmsis_nn.yaml \
  --jlink-serial <APOLLO510_JLINK_SERIAL>
~~~

The configuration includes CPU, MVE, and memory counter passes. Its PMU
firmware checks PMU initialization and counter reads, runs a CPU-cycle
self-test before capture, and distinguishes a normal 16-bit chained-counter
carry from a true 32-bit overflow. The result bundle contains the aggregated
per-instruction counters and clean total/average inference cycles. Update the
PTE operator lists and the explicit input, output, and arena sizes when using a
different model.

On 2026-08-13, the identical regenerated PTE measured 5,180,417 clean cycles with Arm CMSIS-NN and 5,142,467 with ns-cmsis-nn on Apollo510; ns-cmsis-nn was 37,950 cycles (0.73%) faster.

## Run on Apollo510 EVB

~~~bash
uv run nsx flash examples/executorch_cmsis_nn --board apollo510_evb --build-dir examples/executorch_cmsis_nn/build/resnet8 --target executorch_cmsis_nn
~~~

The application exports these debugger-visible RAM symbols:

- executorch_cmsis_nn_status: 0 while pending, 1 on success, high bit set on failure.
- executorch_cmsis_nn_error: the ExecuTorch error code.
- executorch_cmsis_nn_max_error_micro: maximum absolute output error multiplied by one million.

If automatic probe selection fails, select the detected J-Link serial explicitly.
