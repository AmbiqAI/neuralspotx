# ExecuTorch Cortex-M CMSIS-NN runner validation

This application validates the NSX ExecuTorch runner on an Apollo510 EVB. It does not create, export, quantize, or lower a model. It consumes a prebuilt ExecuTorch PTE and packages that PTE into the board firmware.

The included fixture is model/resnet8_cmsis_nn.pte, a 172 KB MLPerf Tiny-style ResNet-8 PTE for 32x32 RGB input and 10-class output. It is treated as an opaque runner input.

## Responsibility boundary

Before NSX:

1. A model owner creates a PTE using their chosen ExecuTorch export pipeline.
2. The model owner supplies the PTE, its required operator list, and its input/output contract.

Inside NSX:

1. NSX resolves the ExecuTorch, board, CMSIS-NN, and CMSIS dependencies.
2. CMake converts the supplied PTE bytes into a read-only C array stored in firmware flash. This packaging step does not modify or compile the PTE.
3. Selective code generation registers the Cortex-M operators named by NSX_EXECUTORCH_CORTEX_M_SELECT_OPS_LIST and the portable ATen fallback operators named by NSX_EXECUTORCH_PORTABLE_SELECT_OPS_LIST.
4. The linker combines the PTE, standard ExecuTorch runtime, selected portable kernels, Cortex-M operator implementations, upstream CMSIS-NN, and Apollo510 board support.
5. main.cc passes the embedded PTE and caller-owned memory arenas to nsx::executorch::run_once.

The nsx-executorch module uses the standard ExecuTorch lifecycle: load Program, inspect the forward method, create MemoryManager objects, load the method, set inputs, execute, and retrieve outputs.

## Supplied fixture contract

The included PTE requires:

- cortex_m::quantize_per_tensor.out
- cortex_m::quantized_conv2d.out
- cortex_m::quantized_add.out
- cortex_m::quantized_avg_pool2d.out
- cortex_m::dequantize_per_tensor.out

Those Cortex-M operators call upstream Arm CMSIS-NN functions including arm_convolve_wrapper_s8, arm_elementwise_add_s8, and arm_avgpool_s8. This ResNet-8 PTE does not itself require portable operators. The example nevertheless prelinks the additional kernels found in a larger ResNet18 graph: the Cortex-M max-pool and transpose operators plus the portable aten::clamp.out and aten::addmm.out fallbacks. This validates that NSX can compose Cortex-M and portable kernels in one firmware image without enabling the entire portable operator library.

The fixture-specific input and expected output live in src/validation_data.h. A different contract can be supplied with NSX_EXECUTORCH_VALIDATION_HEADER. The runner compares all 10 output logits against that supplied reference. These values are validation data, not model-export code.

The Apollo510 hardware run on 2026-08-10 returned status 1, ExecuTorch error 0, and maximum numerical error 0.

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

On the Apollo510 EVB, the runner returned status 1, ExecuTorch error 0, and maximum absolute error 0 against the upstream-generated reference output. This validates runtime execution and CMSIS-NN kernel integration. The example model uses random weights, so this is not an application-accuracy measurement.

## Build through NSX

This is currently a two-checkout development example: nsx.yml points to an adjacent nsx-executorch checkout. From the NeuralSPOT-X repository root:

~~~bash
uv run nsx lock --app examples/executorch_cmsis_nn
uv run nsx sync --app examples/executorch_cmsis_nn
uv run nsx configure examples/executorch_cmsis_nn --board apollo510_evb --build-dir examples/executorch_cmsis_nn/build/resnet8
uv run nsx build examples/executorch_cmsis_nn --board apollo510_evb --build-dir examples/executorch_cmsis_nn/build/resnet8
~~~

The successful build verifies that the final ELF contains the selected ExecuTorch Cortex-M and portable implementations plus the required CMSIS-NN functions. The additional kernels increase firmware text size but do not materially change the ResNet-8 runner arena requirements.

## Run on Apollo510 EVB

~~~bash
uv run nsx flash examples/executorch_cmsis_nn --board apollo510_evb --build-dir examples/executorch_cmsis_nn/build/resnet8 --target executorch_cmsis_nn
~~~

The application exports these debugger-visible RAM symbols:

- executorch_cmsis_nn_status: 0 while pending, 1 on success, high bit set on failure.
- executorch_cmsis_nn_error: the ExecuTorch error code.
- executorch_cmsis_nn_max_error_micro: maximum absolute output error multiplied by one million.

If automatic probe selection fails, select the detected J-Link serial explicitly.
