# ExecuTorch Cortex-M CMSIS-NN runner validation

This application validates the NSX ExecuTorch runner on an Apollo510 EVB. It does not create, export, quantize, or lower a model. It consumes a prebuilt ExecuTorch PTE and packages that PTE into the board firmware.

The included fixture is model/resnet8_cmsis_nn.pte, a 172 KB MLPerf Tiny-style ResNet-8 PTE for 32x32 RGB input and 10-class output. It is treated as an opaque runner input.

## Responsibility boundary

Before NSX:

1. A model owner creates a PTE using their chosen ExecuTorch export pipeline.
2. The model owner supplies the PTE, its required operator list, and its input/output contract.

Inside NSX:

1. NSX authenticates to the private `nsx-executorch@v0.1.2` project and locks
   its exact source artifact.
2. CMake converts the supplied PTE bytes into a read-only C array stored in firmware flash. This packaging step does not modify or compile the PTE.
3. Selective code generation registers the Cortex-M operators named by NSX_EXECUTORCH_CORTEX_M_SELECT_OPS_LIST and the portable ATen fallback operators named by NSX_EXECUTORCH_PORTABLE_SELECT_OPS_LIST.
4. The linker combines the PTE, unmodified ExecuTorch runtime, selected portable kernels, stock Cortex-M operators, stock CMSIS-NN, and Apollo510 board support.
5. main.cc passes the embedded PTE and caller-owned memory arenas to nsx::executorch::run_once_profiled.

The nsx-executorch module uses the standard ExecuTorch lifecycle: load Program, inspect the forward method, create MemoryManager objects, load the method, set inputs, execute, and retrieve outputs.

## Supplied fixture contract

The included PTE requires:

- cortex_m::quantize_per_tensor.out
- cortex_m::quantized_conv2d.out
- cortex_m::quantized_add.out
- cortex_m::quantized_avg_pool2d.out
- cortex_m::dequantize_per_tensor.out

Those Cortex-M operators call stock CMSIS-NN functions including arm_convolve_wrapper_s8, arm_elementwise_add_s8, and arm_avgpool_s8. This ResNet-8 PTE does not itself require portable operators. The example nevertheless prelinks the additional kernels found in a larger ResNet18 graph: the Cortex-M max-pool and transpose operators plus the portable aten::clamp.out and aten::addmm.out fallbacks. This validates that NSX can compose Cortex-M and portable kernels in one firmware image without enabling the entire portable operator library.

The fixture-specific input and expected output live in src/validation_data.h. A different contract can be supplied with NSX_EXECUTORCH_VALIDATION_HEADER. The runner compares all 10 output logits against that supplied reference. These values are validation data, not model-export code.

The Apollo510 hardware run on 2026-08-16 returned status 1, ExecuTorch error 0, and maximum numerical error 0.

## Cycle profiling

The example enables ExecuTorch's native EventTracer integration. The runner
reports total `Method::execute()` cycles and records one measurement for every
operator call. Each record contains its operator kind, chain index, instruction
index, and elapsed DWT cycles. These identifiers can be mapped to model export
metadata by Helia Profiler.

On Cortex-M55, DWT CYCCNT aliases the PMU cycle counter. The packaged runtime
enables the Apollo510 debug clock, PMU, and cycle counter itself. The example
also performs the normal NSX system initialization, including BSP setup,
I/D-cache enablement, LP mode at 96 MHz, and the SpotManager profiling
configuration. Measurements therefore do not depend on an attached debugger.
After the timed region, the example cleans D-cache so J-Link reads the same
completed arrays printed over ITM.

The standalone 2026-08-16 run, with J-Link disconnected during inference,
reported 5,178,609 total cycles. The 16 operator intervals summed to
5,173,144 cycles, leaving 5,465 cycles of executor and callback overhead:

| Instruction | ResNet-8 operation | Cycles |
| ---: | --- | ---: |
| 0 | input quantize | 13,863 |
| 1 | entry conv | 740,434 |
| 2 | stage 0 conv 1 | 997,184 |
| 3 | stage 0 conv 2 | 997,202 |
| 4 | stage 0 residual add | 218,735 |
| 5 | stage 1 conv 1 | 412,786 |
| 6 | stage 1 conv 2 | 611,335 |
| 7 | stage 1 skip conv | 156,055 |
| 8 | stage 1 residual add | 109,311 |
| 9 | stage 2 conv 1 | 282,488 |
| 10 | stage 2 conv 2 | 473,574 |
| 11 | stage 2 skip conv | 91,776 |
| 12 | stage 2 residual add | 55,090 |
| 13 | global average pool | 9,742 |
| 14 | classifier (lowered as Conv2D) | 2,318 |
| 15 | output dequantize | 1,251 |

The post-link verifier checks that the firmware contains the EventTracer-backed
profiling runner and stock CMSIS-NN archive. It also rejects the old
ns-cmsis-nn-only weight-sum API.

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

The reusable nsx::executorch profiling API itself is model-independent. The example application around it is necessarily model-aware because it owns the input and output buffers.

## Build through NSX

The module registry entry uses the private, immutable
`AmbiqAI/nsx-executorch@v0.1.2` release. Authenticate Git for that repository
before locking or syncing. From the NeuralSPOT-X repository root:

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
- executorch_cmsis_nn_execution_cycles: cycles spent in Method::execute().
- executorch_cmsis_nn_operator_count: number of captured operator calls.
- executorch_cmsis_nn_operator_kind/chain/instruction: runtime operator identifiers.
- executorch_cmsis_nn_operator_cycles: per-operator elapsed cycles.

If automatic probe selection fails, select the detected J-Link serial explicitly.
