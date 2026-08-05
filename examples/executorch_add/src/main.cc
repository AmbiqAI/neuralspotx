#include <cstddef>
#include <cstdint>

#include "model_pte.h"
#include "nsx_core.h"
#include "nsx_executorch.h"

namespace {

alignas(16) std::uint8_t method_arena[32 * 1024];
alignas(16) std::uint8_t planned_arena[32 * 1024];
alignas(16) std::uint8_t temporary_arena[8 * 1024];
alignas(16) float input_a[64];
alignas(16) float input_b[64];
alignas(16) float output[64];

}  // namespace

int main() {
  nsx_core_config_t config = {.api = &nsx_core_V1_0_0};
  (void)nsx_core_init(&config);
  nsx_itm_printf_enable();

  for (std::size_t index = 0; index < 64; ++index) {
    input_a[index] = 1.0F;
    input_b[index] = 2.0F;
    output[index] = 0.0F;
  }

  const nsx::executorch::Buffer inputs[] = {
      {input_a, sizeof(input_a)},
      {input_b, sizeof(input_b)},
  };
  nsx::executorch::Buffer outputs[] = {{output, sizeof(output)}};

  const auto result = nsx::executorch::run_once(
      model_pte, sizeof(model_pte),
      {method_arena, sizeof(method_arena)},
      {planned_arena, sizeof(planned_arena)},
      {temporary_arena, sizeof(temporary_arena)}, inputs, 2, outputs, 1);

  while (true) {
    if (!result.ok()) {
      nsx_printf("EXECUTORCH_FAIL stage=%s error=0x%08lx inputs=%lu outputs=%lu planned=%lu\r\n",
                 nsx::executorch::stage_name(result.stage),
                 static_cast<unsigned long>(result.executorch_error),
                 static_cast<unsigned long>(result.input_count),
                 static_cast<unsigned long>(result.output_count),
                 static_cast<unsigned long>(result.planned_bytes_required));
    } else {
      nsx_printf("EXECUTORCH_OK output0_milli=%ld bytes=%lu planned=%lu\r\n",
                 static_cast<long>(output[0] * 1000.0F),
                 static_cast<unsigned long>(outputs[0].size),
                 static_cast<unsigned long>(result.planned_bytes_required));
    }
    nsx_delay_us(1000000);
  }
}
