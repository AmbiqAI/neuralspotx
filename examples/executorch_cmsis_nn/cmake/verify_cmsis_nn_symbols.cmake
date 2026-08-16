if(NOT DEFINED NM OR NOT DEFINED ELF OR NOT DEFINED MAP)
  message(FATAL_ERROR "NM, ELF, and MAP are required")
endif()
if(NOT EXISTS "${MAP}")
  message(FATAL_ERROR "Linker map does not exist: ${MAP}")
endif()

file(READ "${MAP}" map_output)
set(provider_archive_marker
  "nsx_executorch/executorch/backends/cortex_m/_deps/cmsis_nn-build/libcmsis-nn.a")
string(FIND "${map_output}" "${provider_archive_marker}" provider_archive_index)
if(provider_archive_index EQUAL -1)
  message(FATAL_ERROR
    "${ELF} did not link stock CMSIS-NN from nsx-executorch (${provider_archive_marker})")
endif()

execute_process(
  COMMAND "${NM}" -C --defined-only "${ELF}"
  RESULT_VARIABLE nm_result
  OUTPUT_VARIABLE nm_output
  ERROR_VARIABLE nm_error
)
if(NOT nm_result EQUAL 0)
  message(FATAL_ERROR "Failed to inspect ${ELF}: ${nm_error}")
endif()

function(require_symbol operator symbol description)
  string(FIND ",${CORTEX_M_OPS}," ",${operator}," operator_index)
  if(NOT operator_index EQUAL -1)
    string(FIND "${nm_output}" "${symbol}" symbol_index)
    if(symbol_index EQUAL -1)
      message(FATAL_ERROR
        "${ELF} does not contain ${description} required by ${operator}")
    endif()
  endif()
endfunction()

function(require_portable_symbol operator symbol)
  string(FIND ",${PORTABLE_OPS}," ",${operator}," operator_index)
  if(NOT operator_index EQUAL -1)
    string(FIND "${nm_output}" "${symbol}" symbol_index)
    if(symbol_index EQUAL -1)
      message(FATAL_ERROR
        "${ELF} does not contain portable kernel ${symbol} required by ${operator}")
    endif()
  endif()
endfunction()

function(require_runtime_symbol symbol description)
  string(FIND "${nm_output}" "${symbol}" symbol_index)
  if(symbol_index EQUAL -1)
    message(FATAL_ERROR "${ELF} does not contain ${description}")
  endif()
endfunction()

function(forbid_symbol symbol description)
  string(FIND "${nm_output}" "${symbol}" symbol_index)
  if(NOT symbol_index EQUAL -1)
    message(FATAL_ERROR "${ELF} unexpectedly contains ${description}")
  endif()
endfunction()

require_symbol("cortex_m::quantized_conv2d.out"
  "cortex_m::native::quantized_conv2d_out(" "the Cortex-M Conv2D kernel")
require_symbol("cortex_m::quantized_conv2d.out"
  "arm_convolve_wrapper_s8" "the CMSIS-NN Conv2D kernel")
require_symbol("cortex_m::quantized_depthwise_conv2d.out"
  "cortex_m::native::quantized_depthwise_conv2d_out("
  "the Cortex-M depthwise Conv2D kernel")
require_symbol("cortex_m::quantized_depthwise_conv2d.out"
  "arm_depthwise_conv_wrapper_s8" "the CMSIS-NN depthwise Conv2D kernel")
require_symbol("cortex_m::quantized_linear.out"
  "cortex_m::native::quantized_linear_out(" "the Cortex-M linear kernel")
require_symbol("cortex_m::quantized_linear.out"
  "arm_fully_connected_s8" "the CMSIS-NN fully connected kernel")
require_symbol("cortex_m::quantized_add.out"
  "cortex_m::native::quantized_add_out(" "the Cortex-M add kernel")
require_symbol("cortex_m::quantized_add.out"
  "arm_elementwise_add_s8" "the CMSIS-NN add kernel")
require_symbol("cortex_m::quantized_avg_pool2d.out"
  "cortex_m::native::quantized_avg_pool2d_out("
  "the Cortex-M average-pool kernel")
require_symbol("cortex_m::quantized_avg_pool2d.out"
  "arm_avgpool_s8" "the CMSIS-NN average-pool kernel")
require_symbol("cortex_m::quantized_max_pool2d.out"
  "cortex_m::native::quantized_max_pool2d_out(" "the Cortex-M max-pool kernel")
require_symbol("cortex_m::quantized_max_pool2d.out"
  "arm_max_pool_s8" "the CMSIS-NN max-pool kernel")
require_symbol("cortex_m::transpose.out"
  "cortex_m::native::transpose_out(" "the Cortex-M transpose kernel")

require_portable_symbol("aten::clamp.out" "torch::executor::native::clamp_out(")
require_portable_symbol("aten::addmm.out" "torch::executor::native::addmm_out(")

require_runtime_symbol("nsx::executorch::run_once_profiled("
  "the NSX ExecuTorch profiling runner")
require_runtime_symbol("OperatorEventTracer::start_profiling("
  "the stock ExecuTorch EventTracer callback")
forbid_symbol("arm_convolve_s8_get_weights_sum_size"
  "the ns-cmsis-nn-only convolution weight-sum API")

message(STATUS
  "Verified stock ExecuTorch profiling, Cortex-M, portable, and CMSIS-NN symbols in ${ELF}")
