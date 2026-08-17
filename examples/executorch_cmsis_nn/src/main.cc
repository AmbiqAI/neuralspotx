#include <cmath>
#include <cstddef>
#include <cstdint>

#include "am_mcu_apollo.h"
#include "model_pte.h"
#include "nsx_core.h"
#include "nsx_executorch.h"
#include "nsx_system.h"

#ifndef NSX_EXECUTORCH_VALIDATION_HEADER
#define NSX_EXECUTORCH_VALIDATION_HEADER "validation_data.h"
#endif
#include NSX_EXECUTORCH_VALIDATION_HEADER

namespace validation = executorch_cmsis_nn_validation;

extern "C" {
volatile std::uint32_t executorch_cmsis_nn_status = 0;
volatile std::uint32_t executorch_cmsis_nn_error = 0;
volatile std::uint32_t executorch_cmsis_nn_max_error_micro = 0;
volatile std::uint32_t executorch_cmsis_nn_execution_cycles = 0;
volatile std::uint32_t executorch_cmsis_nn_operator_count = 0;
volatile std::uint32_t executorch_cmsis_nn_operator_kind[64] = {};
volatile std::int32_t executorch_cmsis_nn_operator_chain[64] = {};
volatile std::uint32_t executorch_cmsis_nn_operator_instruction[64] = {};
volatile std::uint32_t executorch_cmsis_nn_operator_cycles[64] = {};
}

namespace {

alignas(16) std::uint8_t method_arena[64 * 1024];
alignas(16) std::uint8_t planned_arena[160 * 1024];
alignas(16) std::uint8_t temporary_arena[32 * 1024];
alignas(16) float input[validation::kInputElementCount];
alignas(16) float output[validation::kOutputElementCount];
std::uint32_t operator_start_cycles[64] = {};

std::uint32_t begin_operator(void *,
                             const nsx::executorch::OperatorEvent &event) {
  const std::uint32_t index = executorch_cmsis_nn_operator_count;
  if (index >= 64) {
    return 64;
  }
  executorch_cmsis_nn_operator_kind[index] =
      static_cast<std::uint32_t>(event.kind);
  executorch_cmsis_nn_operator_chain[index] = event.chain_index;
  executorch_cmsis_nn_operator_instruction[index] = event.instruction_index;
  operator_start_cycles[index] = DWT->CYCCNT;
  executorch_cmsis_nn_operator_count = index + 1;
  return index;
}

void end_operator(void *, std::uint32_t handle) {
  if (handle < 64) {
    executorch_cmsis_nn_operator_cycles[handle] =
        DWT->CYCCNT - operator_start_cycles[handle];
  }
}

} // namespace

int main() {
  nsx_system_config_t config = {};
  config.perf_mode = NSX_PERF_LOW;
  config.enable_cache = true;
  config.enable_sram = true;
  config.debug.transport = NSX_DEBUG_ITM;
  config.skip_bsp_init = false;
  config.spot_mgr_profile = true;
  const std::uint32_t initialization_status = nsx_system_init(&config);
  if (initialization_status != NSX_STATUS_SUCCESS) {
    executorch_cmsis_nn_error = initialization_status;
    executorch_cmsis_nn_status = 0x80000200UL;
    while (true) {
      nsx_delay_us(1000000);
    }
  }

  for (std::size_t index = 0; index < validation::kInputElementCount; ++index) {
    input[index] = validation::kInput[index];
  }
  for (float &value : output) {
    value = 0.0F;
  }

  const nsx::executorch::Buffer inputs[] = {{input, sizeof(input)}};
  nsx::executorch::Buffer outputs[] = {{output, sizeof(output)}};
  const nsx::executorch::ProfilingCallbacks profiling = {
      nullptr, begin_operator, end_operator};
  const auto result = nsx::executorch::run_once_profiled(
      model_pte, sizeof(model_pte), {method_arena, sizeof(method_arena)},
      {planned_arena, sizeof(planned_arena)},
      {temporary_arena, sizeof(temporary_arena)}, inputs, 1, outputs, 1,
      &profiling);
  executorch_cmsis_nn_execution_cycles = result.execution_cycles;

  float max_error = 0.0F;
  std::size_t max_error_index = 0;
  bool output_matches = result.ok() && outputs[0].size == sizeof(output);
  if (output_matches) {
    for (std::size_t index = 0; index < validation::kOutputElementCount;
         ++index) {
      float error = output[index] - validation::kExpectedOutput[index];
      if (error < 0.0F) {
        error = -error;
      }
      if (!std::isfinite(error)) {
        output_matches = false;
        max_error = validation::kTolerance + 1.0F;
        max_error_index = index;
        continue;
      }
      if (error > max_error) {
        max_error = error;
        max_error_index = index;
      }
      if (error > validation::kTolerance) {
        output_matches = false;
      }
    }
  }

  executorch_cmsis_nn_error = result.executorch_error;
  executorch_cmsis_nn_max_error_micro =
      static_cast<std::uint32_t>(max_error * 1000000.0F);
  if (!result.ok()) {
    executorch_cmsis_nn_status =
        0x80000000UL | static_cast<std::uint32_t>(result.stage);
  } else if (!output_matches) {
    executorch_cmsis_nn_status = 0x80000100UL;
  } else {
    executorch_cmsis_nn_status = 1;
  }

  // The debugger reads SRAM without participating in the Cortex-M55 data
  // cache. Publish the completed counters after the timed region so J-Link
  // always observes the same values printed over ITM.
  __DSB();
  SCB_CleanDCache();
  __DSB();

  while (true) {
    if (!result.ok()) {
      nsx_printf("EXECUTORCH_CMSIS_NN_FAIL stage=%s error=0x%08lx inputs=%lu "
                 "outputs=%lu planned=%lu\r\n",
                 nsx::executorch::stage_name(result.stage),
                 static_cast<unsigned long>(result.executorch_error),
                 static_cast<unsigned long>(result.input_count),
                 static_cast<unsigned long>(result.output_count),
                 static_cast<unsigned long>(result.planned_bytes_required));
    } else if (!output_matches) {
      nsx_printf(
          "EXECUTORCH_CMSIS_NN_FAIL stage=compare max_error_micro=%lu "
          "index=%lu tolerance_micro=%lu bytes=%lu\r\n",
          static_cast<unsigned long>(max_error * 1000000.0F),
          static_cast<unsigned long>(max_error_index),
          static_cast<unsigned long>(validation::kTolerance * 1000000.0F),
          static_cast<unsigned long>(outputs[0].size));
    } else {
      nsx_printf(
          "EXECUTORCH_CMSIS_NN_OK max_error_micro=%lu tolerance_micro=%lu "
          "bytes=%lu planned=%lu cycles=%lu operators=%lu\r\n",
          static_cast<unsigned long>(max_error * 1000000.0F),
          static_cast<unsigned long>(validation::kTolerance * 1000000.0F),
          static_cast<unsigned long>(outputs[0].size),
          static_cast<unsigned long>(result.planned_bytes_required),
          static_cast<unsigned long>(result.execution_cycles),
          static_cast<unsigned long>(executorch_cmsis_nn_operator_count));
      for (std::uint32_t index = 0; index < executorch_cmsis_nn_operator_count;
           ++index) {
        nsx_printf("EXECUTORCH_OP index=%lu kind=%lu chain=%ld instruction=%lu "
                   "cycles=%lu\r\n",
                   static_cast<unsigned long>(index),
                   static_cast<unsigned long>(
                       executorch_cmsis_nn_operator_kind[index]),
                   static_cast<long>(executorch_cmsis_nn_operator_chain[index]),
                   static_cast<unsigned long>(
                       executorch_cmsis_nn_operator_instruction[index]),
                   static_cast<unsigned long>(
                       executorch_cmsis_nn_operator_cycles[index]));
      }
    }
    nsx_delay_us(1000000);
  }
}
