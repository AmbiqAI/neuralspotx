#include <cstddef>
#include <cstdint>
#include <cmath>

#include "model_pte.h"
#include "nsx_core.h"
#include "nsx_executorch.h"
#include "validation_data.h"

namespace validation = executorch_cmsis_nn_validation;

extern "C" {
volatile std::uint32_t executorch_cmsis_nn_status = 0;
volatile std::uint32_t executorch_cmsis_nn_error = 0;
volatile std::uint32_t executorch_cmsis_nn_max_error_micro = 0;
}

namespace {

alignas(16) std::uint8_t method_arena[32 * 1024];
alignas(16) std::uint8_t planned_arena[32 * 1024];
alignas(16) std::uint8_t temporary_arena[8 * 1024];
alignas(16) float input[validation::kInputElementCount];
alignas(16) float output[validation::kOutputElementCount];

}  // namespace

int main() {
  nsx_core_config_t config = {.api = &nsx_core_V1_0_0};
  (void)nsx_core_init(&config);
  nsx_itm_printf_enable();

  for (std::size_t index = 0; index < validation::kInputElementCount; ++index) {
    input[index] = validation::kInput[index];
  }
  for (float& value : output) {
    value = 0.0F;
  }

  const nsx::executorch::Buffer inputs[] = {{input, sizeof(input)}};
  nsx::executorch::Buffer outputs[] = {{output, sizeof(output)}};
  const auto result = nsx::executorch::run_once(
      model_pte, sizeof(model_pte), {method_arena, sizeof(method_arena)},
      {planned_arena, sizeof(planned_arena)},
      {temporary_arena, sizeof(temporary_arena)}, inputs, 1, outputs, 1);

  float max_error = 0.0F;
  std::size_t max_error_index = 0;
  bool output_matches = result.ok() && outputs[0].size == sizeof(output);
  if (output_matches) {
    for (std::size_t index = 0; index < validation::kOutputElementCount; ++index) {
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

  while (true) {
    if (!result.ok()) {
      nsx_printf(
          "EXECUTORCH_CMSIS_NN_FAIL stage=%s error=0x%08lx inputs=%lu "
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
          "bytes=%lu planned=%lu\r\n",
          static_cast<unsigned long>(max_error * 1000000.0F),
          static_cast<unsigned long>(validation::kTolerance * 1000000.0F),
          static_cast<unsigned long>(outputs[0].size),
          static_cast<unsigned long>(result.planned_bytes_required));
    }
    nsx_delay_us(1000000);
  }
}
