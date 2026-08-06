if(NOT DEFINED NM OR NOT DEFINED ELF)
  message(FATAL_ERROR "NM and ELF are required")
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

string(FIND "${nm_output}"
       "cortex_m::native::quantized_conv2d_out(" cortex_m_symbol_index)
if(cortex_m_symbol_index EQUAL -1)
  message(FATAL_ERROR
    "${ELF} does not contain the ExecuTorch Cortex-M Conv2D implementation")
endif()

string(FIND "${nm_output}" " T arm_convolve_wrapper_s8\n" cmsis_nn_symbol_index)
if(cmsis_nn_symbol_index EQUAL -1)
  message(FATAL_ERROR
    "${ELF} does not contain the CMSIS-NN arm_convolve_wrapper_s8 function")
endif()

message(STATUS "Verified ExecuTorch Cortex-M and CMSIS-NN Conv2D symbols in ${ELF}")
