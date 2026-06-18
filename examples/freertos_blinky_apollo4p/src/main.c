#include "nsx_core.h"
#include "nsx_freertos.h"

#include "FreeRTOS.h"
#include "task.h"

#define BLINK_TASK_STACK_WORDS (configMINIMAL_STACK_SIZE * 2)
#define BLINK_TASK_PRIORITY    (tskIDLE_PRIORITY + 1)

static void blink_task(void *arg)
{
    (void)arg;
    uint32_t count = 0;
    for (;;) {
        nsx_printf("freertos_blinky: tick %lu (kernel %s)\r\n",
                   (unsigned long)count++, nsx_freertos_kernel_version());
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

int main(void)
{
    nsx_core_config_t cfg = {
        .api = &nsx_core_V1_0_0,
    };
    (void)nsx_core_init(&cfg);

    nsx_itm_printf_enable();
    nsx_printf("freertos_blinky: starting scheduler\r\n");

    if (xTaskCreate(blink_task, "blink", BLINK_TASK_STACK_WORDS, NULL,
                    BLINK_TASK_PRIORITY, NULL) != pdPASS) {
        nsx_printf("freertos_blinky: task create failed\r\n");
        for (;;) {
        }
    }

    nsx_freertos_start();

    /* vTaskStartScheduler() does not return unless the kernel ran out of heap. */
    for (;;) {
    }
}

/* configUSE_MALLOC_FAILED_HOOK == 1 requires this application hook. */
void vApplicationMallocFailedHook(void)
{
    nsx_printf("freertos_blinky: malloc failed\r\n");
    taskDISABLE_INTERRUPTS();
    for (;;) {
    }
}

/* configCHECK_FOR_STACK_OVERFLOW != 0 requires this application hook. */
void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName)
{
    (void)xTask;
    nsx_printf("freertos_blinky: stack overflow in %s\r\n", pcTaskName);
    taskDISABLE_INTERRUPTS();
    for (;;) {
    }
}
