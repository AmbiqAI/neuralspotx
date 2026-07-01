/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026, Ambiq */
/*
 * ble_webble: minimal NSX BLE peripheral on Apollo4 Blue Plus (Cooper).
 *
 * Demonstrates nsx-ble / nsx-cordio bring-up. In keeping with NSX philosophy,
 * ALL policy is owned here in the app: baseline board power-up, the WSF buffer
 * pool, the FreeRTOS tasks, the dispatcher loop, and radio IRQ priority setup.
 * The modules only provide the BLE stack and the wrapper API.
 *
 * The service exposes three characteristics that a WebBLE / phone client can
 * discover: a read-only heartbeat byte, a notify counter byte, and a
 * read/write RGB value.
 */
#include "nsx_core.h"
#include "FreeRTOS.h"
#include "task.h"
#include "nsx_freertos.h"
#include "am_bsp.h"
#include "ns_ble.h"

/* ---- Service data (app-owned) ---------------------------------------- */
static uint8_t heartbeat_value = 0;    /* read-only: LED heartbeat counter */
static uint8_t notify_value = 0;       /* notify: one byte, no endian parsing */
static uint8_t rgb[3] = {0, 0, 0};     /* read/write */

/* ---- WSF buffer pool (app-owned policy) ------------------------------ */
#define WEBBLE_WSF_BUFFER_POOLS 4
#define WEBBLE_WSF_BUFFER_SIZE                                                  \
    (WEBBLE_WSF_BUFFER_POOLS * 16 + 16 * 8 + 32 * 4 + 64 * 6 + 280 * 14) /      \
        sizeof(uint32_t)

static uint32_t webbleWSFBufferPool[WEBBLE_WSF_BUFFER_SIZE];
static wsfBufPoolDesc_t webbleBufferDescriptors[WEBBLE_WSF_BUFFER_POOLS] = {
    {16, 8}, {32, 4}, {64, 6}, {512, 14}};
static ns_ble_pool_config_t webbleWsfBuffers = {
    .pool = webbleWSFBufferPool,
    .poolSize = sizeof(webbleWSFBufferPool),
    .desc = webbleBufferDescriptors,
    .descNum = WEBBLE_WSF_BUFFER_POOLS};

/* ---- BLE objects ----------------------------------------------------- */
#define webbleUuid(uuid) "19b10000" uuid "537e4f6cd104768a1214"

static ns_ble_service_t webbleService;
static ns_ble_characteristic_t webbleTemperature;
static ns_ble_characteristic_t webbleAccel;
static ns_ble_characteristic_t webbleRgb;

static TaskHandle_t radio_task_handle;
static TaskHandle_t setup_task_handle;
static TaskHandle_t heartbeat_task_handle;

#define WEBBLE_HEARTBEAT_STACK_WORDS 1024
#define WEBBLE_SETUP_STACK_WORDS     2048
#define WEBBLE_RADIO_STACK_WORDS     4096

#define WEBBLE_HEARTBEAT_TASK_PRIORITY (tskIDLE_PRIORITY + 1)
#define WEBBLE_RADIO_TASK_PRIORITY     (tskIDLE_PRIORITY + 3)

/* ---- Characteristic handlers ----------------------------------------- */
static int webbleReadHandler(ns_ble_service_t *s, ns_ble_characteristic_t *c,
                             void *dest) {
    (void)s;
    memcpy(dest, c->applicationValue, c->valueLen);
    return NS_STATUS_SUCCESS;
}

static int webbleWriteHandler(ns_ble_service_t *s, ns_ble_characteristic_t *c,
                              void *src) {
    (void)s;
    memcpy(c->applicationValue, src, c->valueLen);
    nsx_printf("webble: RGB set to %02x%02x%02x\r\n", rgb[0], rgb[1], rgb[2]);
    return NS_STATUS_SUCCESS;
}

static int webbleNotifyHandler(ns_ble_service_t *s, ns_ble_characteristic_t *c) {
    (void)s;
    notify_value++;
    ns_ble_send_value(c, NULL);
    return NS_STATUS_SUCCESS;
}

/* ---- Service definition (runs inside RadioTask) ---------------------- */
static int webble_service_init(void) {
    char webbleName[] = "Webble";

    ns_ble_char2uuid(webbleUuid("0000"), &(webbleService.uuid128));
    memcpy(webbleService.name, webbleName, sizeof(webbleName));
    webbleService.nameLen = sizeof(webbleName) - 1;
    webbleService.baseHandle = 0x0800;
    webbleService.poolConfig = &webbleWsfBuffers;
    webbleService.numAttributes = 0;

    ns_ble_create_characteristic(
        &webbleTemperature, webbleUuid("2001"), &heartbeat_value,
        sizeof(heartbeat_value), NS_BLE_READ, &webbleReadHandler, NULL, NULL, 0,
        false, &(webbleService.numAttributes));

    ns_ble_create_characteristic(
        &webbleAccel, webbleUuid("5001"), &notify_value, sizeof(notify_value),
        NS_BLE_READ | NS_BLE_NOTIFY, NULL, NULL, &webbleNotifyHandler, 200,
        false, &(webbleService.numAttributes));

    ns_ble_create_characteristic(
        &webbleRgb, webbleUuid("8001"), rgb, sizeof(rgb),
        NS_BLE_READ | NS_BLE_WRITE, &webbleReadHandler, &webbleWriteHandler,
        NULL, 0, false, &(webbleService.numAttributes));

    webbleService.numCharacteristics = 3;
    ns_ble_create_service(&webbleService);

    ns_ble_add_characteristic(&webbleService, &webbleTemperature);
    ns_ble_add_characteristic(&webbleService, &webbleAccel);
    ns_ble_add_characteristic(&webbleService, &webbleRgb);

    /* TX power is app policy, not module policy. Cooper's default inside the
     * module is conservative; set this before ns_ble_start_service() kicks
     * DmDevReset(), matching the module's own default-power timing. */
    if (ns_ble_set_tx_power(TX_POWER_LEVEL_PLUS_4P0_dBm) == NS_STATUS_SUCCESS) {
        nsx_printf("webble: TX power set to +4 dBm\r\n");
    } else {
        nsx_printf("webble: TX power set FAILED\r\n");
    }

    ns_ble_start_service(&webbleService);

    return NS_STATUS_SUCCESS;
}

/* ---- Tasks (app-owned) ----------------------------------------------- */
volatile uint32_t g_led_toggle_count = 0; /* readable via JLink memory */
volatile uint32_t g_heartbeat_stack_min_words = 0;
volatile uint32_t g_radio_stack_min_words = 0;
volatile uint32_t g_setup_stack_min_words = 0;

/* LED pins for apollo4p_blue_kxr_evb (D4/D3/D5): all open-drain, active-low.
 * We drive these directly with am_hal_gpio_* instead of going through the
 * am_devices_led wrapper -- fewer moving parts, and it makes the initial
 * state explicit (LEDs start OFF, i.e. output driven high/tristated) rather
 * than inheriting whatever am_devices_led_init() decides "on" means. */
#define WEBBLE_LED0_PIN 16
#define WEBBLE_LED1_PIN 30
#define WEBBLE_LED2_PIN 91

static void heartbeat_task(void *pvParameters) {
    (void)pvParameters;
    uint32_t n = 0;

    am_hal_gpio_pinconfig(WEBBLE_LED0_PIN, am_hal_gpio_pincfg_opendrain);
    am_hal_gpio_pinconfig(WEBBLE_LED1_PIN, am_hal_gpio_pincfg_opendrain);
    am_hal_gpio_pinconfig(WEBBLE_LED2_PIN, am_hal_gpio_pincfg_opendrain);

    /* Active-low LEDs: drive output high (open-drain "off", pulled up
     * externally) so we start from a known OFF state. */
    am_hal_gpio_state_write(WEBBLE_LED0_PIN, AM_HAL_GPIO_OUTPUT_SET);
    am_hal_gpio_state_write(WEBBLE_LED1_PIN, AM_HAL_GPIO_OUTPUT_SET);
    am_hal_gpio_state_write(WEBBLE_LED2_PIN, AM_HAL_GPIO_OUTPUT_SET);

    for (;;) {
        am_hal_gpio_state_write(WEBBLE_LED0_PIN, AM_HAL_GPIO_OUTPUT_TOGGLE);
        am_hal_gpio_state_write(WEBBLE_LED1_PIN, AM_HAL_GPIO_OUTPUT_TOGGLE);
        am_hal_gpio_state_write(WEBBLE_LED2_PIN, AM_HAL_GPIO_OUTPUT_TOGGLE);
        g_led_toggle_count = ++n;
        heartbeat_value = (uint8_t)n;
        g_heartbeat_stack_min_words = uxTaskGetStackHighWaterMark(NULL);
        nsx_printf("webble: heartbeat %lu\r\n", (unsigned long)n);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

static void RadioTask(void *pvParameters) {
    (void)pvParameters;
    nsx_printf("webble: RadioTask start, initializing service\r\n");
    webble_service_init();
    nsx_printf("webble: service started, advertising as 'Webble'\r\n");
    while (1) {
        g_radio_stack_min_words = uxTaskGetStackHighWaterMark(NULL);
        wsfOsDispatcher();
    }
}

static void setup_task(void *pvParameters) {
    (void)pvParameters;
    ns_ble_pre_init(); /* set radio NVIC priorities */
    if (xTaskCreate(RadioTask, "RadioTask", WEBBLE_RADIO_STACK_WORDS, NULL,
                    WEBBLE_RADIO_TASK_PRIORITY, &radio_task_handle) != pdPASS) {
        nsx_printf("webble: RadioTask create failed\r\n");
        taskDISABLE_INTERRUPTS();
        for (;;) {
        }
    }
    g_setup_stack_min_words = uxTaskGetStackHighWaterMark(NULL);
    vTaskSuspend(NULL);
    while (1) {
        ;
    }
}

int main(void) {
    nsx_core_config_t cfg = {.api = &nsx_core_V1_0_0};
    (void)nsx_core_init(&cfg);

    /* Baseline board power-up before touching the radio. App-owned: explicit
     * calls rather than pulling the whole power/timer/interrupt module chain.
     * The Cooper BLE controller manages its own power/reset inside
     * HciDrvRadioBoot().
     *
     * Mirrors legacy neuralSPOT's ns_development_default bring-up
     * (bNeedSharedSRAM=true path): am_bsp_low_power_init() alone only does
     * am_hal_pwrctrl_low_power_init() + SIMOBUCK enable on this board — it does
     * NOT configure DAXI or the cache. Cooper's HciDrvRadioBoot() uploads an
     * ~885KB firmware image out of flash, so a properly configured cache/DAXI
     * matters for that transfer's timing and reliability. */
    am_bsp_low_power_init();

    am_hal_daxi_config_t daxi_cfg = {
        .bDaxiPassThrough = false,
        .bAgingSEnabled = false,
        .eAgingCounter = AM_HAL_DAXI_CONFIG_AGING_1024,
        .eNumBuf = AM_HAL_DAXI_CONFIG_NUMBUF_32,
        .eNumFreeBuf = AM_HAL_DAXI_CONFIG_NUMFREEBUF_3,
    };
    am_hal_daxi_config(&daxi_cfg);

    am_hal_cachectrl_config(&am_hal_cachectrl_defaults);
    am_hal_cachectrl_enable();

    nsx_itm_printf_enable();
    nsx_printf("webble: boot\r\n");
    nsx_interrupt_master_enable();

    if (xTaskCreate(heartbeat_task, "HB", WEBBLE_HEARTBEAT_STACK_WORDS, NULL,
                    WEBBLE_HEARTBEAT_TASK_PRIORITY,
                    &heartbeat_task_handle) != pdPASS) {
        nsx_printf("webble: heartbeat task create failed\r\n");
        for (;;) {
        }
    }

    if (xTaskCreate(setup_task, "Setup", WEBBLE_SETUP_STACK_WORDS, NULL,
                    WEBBLE_RADIO_TASK_PRIORITY, &setup_task_handle) != pdPASS) {
        nsx_printf("webble: setup task create failed\r\n");
        for (;;) {
        }
    }
    nsx_freertos_start(); /* installs CM4F SVC/PendSV/SysTick shims, then starts scheduler */

    for (;;) {
    }
}

/* ---- FreeRTOS hooks (required by this app's FreeRTOSConfig.h) --------- */
void vApplicationMallocFailedHook(void) {
    nsx_printf("webble: malloc failed\r\n");
    taskDISABLE_INTERRUPTS();
    for (;;) {
    }
}

void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName) {
    (void)xTask;
    nsx_printf("webble: stack overflow in %s\r\n", pcTaskName);
    taskDISABLE_INTERRUPTS();
    for (;;) {
    }
}
