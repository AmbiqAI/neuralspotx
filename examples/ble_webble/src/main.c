/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026, Ambiq */
/*
 * ble_webble: minimal NSX BLE peripheral on supported NSX BLE targets.
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
    (WEBBLE_WSF_BUFFER_POOLS * 16 + 16 * 8 + 32 * 4 + 64 * 6 + 512 * 14) /      \
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

#if defined(AM_PART_APOLLO3P) || defined(AM_PART_APOLLO3)
#define WEBBLE_BOARD_MODEL "Apollo3 Blue Plus"
#define WEBBLE_ADV_NAME    "NSX-AP3"
#elif defined(AM_PART_APOLLO4P)
#define WEBBLE_BOARD_MODEL "Apollo4 Blue Plus"
#define WEBBLE_ADV_NAME    "NSX-AP4"
#elif defined(AM_PART_APOLLO510B)
#define WEBBLE_BOARD_MODEL "Apollo510B EVB"
#define WEBBLE_ADV_NAME    "NSX-AP5"
#else
#define WEBBLE_BOARD_MODEL "Ambiq BLE Board"
#define WEBBLE_ADV_NAME    "NSX-BLE"
#endif

static const ns_ble_device_info_t webbleDeviceInfo = {
    .manufacturerName = "Ambiq",
    .modelNumber = WEBBLE_BOARD_MODEL,
    .serialNumber = "chip-derived",
    .firmwareRevision = "5.2.23",
    .hardwareRevision = WEBBLE_BOARD_MODEL,
    .softwareRevision = "ble_webble",
    .vendorIdSource = NS_BLE_DIS_VENDOR_ID_SOURCE_BLUETOOTH_SIG,
    .vendorId = NS_BLE_COMPANY_ID_AMBIQ,
    .productId = 0x0001,
    .productVersion = 0x0001,
};

static const ns_ble_connection_config_t webbleConnectionConfig = {
    .preferredMtu = 247,
    .dataLenTxOctets = 251,
    .dataLenTxTime = 0x0848,
    .connIntervalMin = 24,
    .connIntervalMax = 40,
    .connLatency = 0,
    .supervisionTimeout = 600,
};

static TaskHandle_t radio_task_handle;
static TaskHandle_t setup_task_handle;
static TaskHandle_t heartbeat_task_handle;

typedef enum {
    WEBBLE_STAGE_RESET = 0,
    WEBBLE_STAGE_CORE_INIT = 1,
    WEBBLE_STAGE_BOARD_POWER = 2,
    WEBBLE_STAGE_DAXI = 3,
    WEBBLE_STAGE_CACHE = 4,
    WEBBLE_STAGE_ITM = 5,
    WEBBLE_STAGE_CREATE_HEARTBEAT = 6,
    WEBBLE_STAGE_CREATE_SETUP = 7,
    WEBBLE_STAGE_SCHEDULER = 8,
    WEBBLE_STAGE_BLE_PRE_INIT = 20,
    WEBBLE_STAGE_CREATE_RADIO = 21,
    WEBBLE_STAGE_RADIO_TASK = 30,
    WEBBLE_STAGE_UUID = 31,
    WEBBLE_STAGE_CHARACTERISTICS = 32,
    WEBBLE_STAGE_CREATE_SERVICE = 33,
    WEBBLE_STAGE_ADD_CHARACTERISTICS = 34,
    WEBBLE_STAGE_TX_POWER = 35,
    WEBBLE_STAGE_START_SERVICE = 36,
    WEBBLE_STAGE_WSF_DISPATCH = 37,
} webble_stage_t;

volatile uint32_t g_webble_stage = WEBBLE_STAGE_RESET;
volatile int32_t g_webble_status = NS_STATUS_SUCCESS;

#define WEBBLE_HEARTBEAT_STACK_WORDS 1024
#define WEBBLE_SETUP_STACK_WORDS     2048
#define WEBBLE_RADIO_STACK_WORDS     4096

#define WEBBLE_HEARTBEAT_TASK_PRIORITY (tskIDLE_PRIORITY + 1)
#define WEBBLE_RADIO_TASK_PRIORITY     (tskIDLE_PRIORITY + 3)

static void webble_fail(webble_stage_t stage, int32_t status) {
    g_webble_stage = stage;
    g_webble_status = status;
    nsx_printf("webble: FAIL stage=%lu status=%ld\r\n", (unsigned long)stage,
               (long)status);
    taskDISABLE_INTERRUPTS();
    for (;;) {
    }
}

static void webble_stage(webble_stage_t stage) {
    g_webble_stage = stage;
    g_webble_status = NS_STATUS_SUCCESS;
    nsx_printf("webble: stage %lu\r\n", (unsigned long)stage);
}

static void webble_ble_interrupts_init(void) {
#if defined(AM_PART_APOLLO3P) || defined(AM_PART_APOLLO3)
    NVIC_SetPriority(BLE_IRQn, configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY);
#elif defined(AM_PART_APOLLO4P)
    NVIC_SetPriority(COOPER_IOM_IRQn, 4);
    NVIC_SetPriority(AM_COOPER_IRQn, 4);
#elif defined(AM_PART_APOLLO510B)
    NVIC_SetPriority(AM_BSP_EM9305_RADIO_INT_IRQ, 4);
#endif
}

#if defined(AM_PART_APOLLO3P) || defined(AM_PART_APOLLO3)
void am_ble_isr(void) { ns_ble_handle_controller_irq(); }
#elif defined(AM_PART_APOLLO4P)
void am_cooper_irq_isr(void) { ns_ble_handle_cooper_gpio_irq(); }
#elif defined(AM_PART_APOLLO510B)
void AM_BSP_EM9305_RADIO_INT_ISR(void) { ns_ble_handle_em9305_gpio_irq(AM_BSP_EM9305_RADIO_INT_IRQ); }
#endif

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
    (void)c;
    notify_value++;
    return NS_STATUS_SUCCESS;
}

static void webble_ble_event_handler(const ns_ble_event_t *event, void *context) {
    (void)context;
    switch (event->type) {
    case NS_BLE_EVENT_CONNECTED:
        nsx_printf("webble: connected conn=%u interval=%u latency=%u timeout=%lu\r\n",
                   event->connId, event->value0, event->value1,
                   (unsigned long)event->detail);
        break;
    case NS_BLE_EVENT_DISCONNECTED:
        nsx_printf("webble: disconnected conn=%u reason=0x%02x\r\n", event->connId,
                   event->value0);
        break;
    case NS_BLE_EVENT_MTU_UPDATED:
        nsx_printf("webble: negotiated MTU %u\r\n", event->value0);
        break;
    case NS_BLE_EVENT_DATA_LENGTH_UPDATED:
        nsx_printf("webble: data length Tx=%u Rx=%u\r\n", event->value0, event->value1);
        break;
    case NS_BLE_EVENT_HW_ERROR:
        nsx_printf("webble: hardware error event status=0x%02x\r\n", event->status);
        break;
    default:
        break;
    }
}

/* ---- Service definition (runs inside RadioTask) ---------------------- */
static int webble_service_init(void) {
    char webbleName[] = WEBBLE_ADV_NAME;
    int status;

    webble_stage(WEBBLE_STAGE_UUID);
    ns_ble_char2uuid(webbleUuid("0000"), &(webbleService.uuid128));
    memcpy(webbleService.name, webbleName, sizeof(webbleName));
    webbleService.nameLen = sizeof(webbleName) - 1;
    webbleService.baseHandle = 0x0800;
    webbleService.poolConfig = &webbleWsfBuffers;
    webbleService.numAttributes = 0;
    status = ns_ble_service_set_device_info(&webbleService, &webbleDeviceInfo);
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }
    status = ns_ble_service_set_connection_config(&webbleService, &webbleConnectionConfig);
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }
    ns_ble_service_set_event_handler(&webbleService, webble_ble_event_handler, NULL);

    webble_stage(WEBBLE_STAGE_CHARACTERISTICS);
    status = ns_ble_create_characteristic(
        &webbleTemperature, webbleUuid("2001"), &heartbeat_value,
        sizeof(heartbeat_value), NS_BLE_READ, &webbleReadHandler, NULL, NULL, 0,
        false, &(webbleService.numAttributes));
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }

    status = ns_ble_create_characteristic(
        &webbleAccel, webbleUuid("5001"), &notify_value, sizeof(notify_value),
        NS_BLE_READ | NS_BLE_NOTIFY, NULL, NULL, &webbleNotifyHandler, 200,
        false, &(webbleService.numAttributes));
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }

    status = ns_ble_create_characteristic(
        &webbleRgb, webbleUuid("8001"), rgb, sizeof(rgb),
        NS_BLE_READ | NS_BLE_WRITE, &webbleReadHandler, &webbleWriteHandler,
        NULL, 0, false, &(webbleService.numAttributes));
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }
    /* RGB is exactly 3 bytes; reject short/long ATT writes before the callback copies. */
    webbleRgb.value.settings &= ~ATTS_SET_VARIABLE_LEN;

    webbleService.numCharacteristics = 3;
    webble_stage(WEBBLE_STAGE_CREATE_SERVICE);
    status = ns_ble_create_service(&webbleService);
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }

    webble_stage(WEBBLE_STAGE_ADD_CHARACTERISTICS);
    status = ns_ble_add_characteristic(&webbleService, &webbleTemperature);
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }
    status = ns_ble_add_characteristic(&webbleService, &webbleAccel);
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }
    status = ns_ble_add_characteristic(&webbleService, &webbleRgb);
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }

    /* TX power is app policy, not module policy. Set this before
     * ns_ble_start_service() kicks DmDevReset(), matching the module's own
     * default-power timing. */
#if defined(AM_PART_APOLLO3P) || defined(AM_PART_APOLLO3)
    webble_stage(WEBBLE_STAGE_TX_POWER);
    if (ns_ble_set_tx_power(TX_POWER_LEVEL_PLUS_3P0_dBm) == NS_STATUS_SUCCESS) {
        nsx_printf("webble: TX power set to +3 dBm\r\n");
    } else {
        return NS_STATUS_FAILURE;
    }
#else
    webble_stage(WEBBLE_STAGE_TX_POWER);
    if (ns_ble_set_tx_power(TX_POWER_LEVEL_PLUS_4P0_dBm) == NS_STATUS_SUCCESS) {
        nsx_printf("webble: TX power set to +4 dBm\r\n");
    } else {
        return NS_STATUS_FAILURE;
    }
#endif

    webble_stage(WEBBLE_STAGE_START_SERVICE);
    status = ns_ble_start_service(&webbleService);
    if (status != NS_STATUS_SUCCESS) {
        return status;
    }

    return NS_STATUS_SUCCESS;
}

/* ---- Tasks (app-owned) ----------------------------------------------- */
volatile uint32_t g_led_toggle_count = 0; /* readable via JLink memory */
volatile uint32_t g_heartbeat_stack_min_words = 0;
volatile uint32_t g_radio_stack_min_words = 0;
volatile uint32_t g_setup_stack_min_words = 0;

/* LED pins are app policy. Use direct HAL GPIO so the heartbeat has no module
 * dependency beyond the board BSP pin definitions. */
#if defined(AM_PART_APOLLO3P) || defined(AM_PART_APOLLO3)
#define WEBBLE_LED0_PIN AM_BSP_GPIO_LED0
#define WEBBLE_LED1_PIN AM_BSP_GPIO_LED1
#define WEBBLE_LED2_PIN AM_BSP_GPIO_LED2
#define WEBBLE_LED0_CFG g_AM_BSP_GPIO_LED0
#define WEBBLE_LED1_CFG g_AM_BSP_GPIO_LED1
#define WEBBLE_LED2_CFG g_AM_BSP_GPIO_LED2
#define WEBBLE_LEDS_ACTIVE_LOW 0
#elif defined(AM_PART_APOLLO4P)
#define WEBBLE_LED0_PIN 16
#define WEBBLE_LED1_PIN 30
#define WEBBLE_LED2_PIN 91
#define WEBBLE_LED0_CFG am_hal_gpio_pincfg_opendrain
#define WEBBLE_LED1_CFG am_hal_gpio_pincfg_opendrain
#define WEBBLE_LED2_CFG am_hal_gpio_pincfg_opendrain
#define WEBBLE_LEDS_ACTIVE_LOW 1
#elif defined(AM_PART_APOLLO510B)
#define WEBBLE_LED0_PIN AM_BSP_GPIO_LED0
#define WEBBLE_LED1_PIN AM_BSP_GPIO_LED1
#define WEBBLE_LED2_PIN AM_BSP_GPIO_LED2
#define WEBBLE_LED0_CFG g_AM_BSP_GPIO_LED0
#define WEBBLE_LED1_CFG g_AM_BSP_GPIO_LED1
#define WEBBLE_LED2_CFG g_AM_BSP_GPIO_LED2
#define WEBBLE_LEDS_ACTIVE_LOW 1
#endif

static void heartbeat_task(void *pvParameters) {
    (void)pvParameters;
    uint32_t n = 0;

    am_hal_gpio_pinconfig(WEBBLE_LED0_PIN, WEBBLE_LED0_CFG);
    am_hal_gpio_pinconfig(WEBBLE_LED1_PIN, WEBBLE_LED1_CFG);
    am_hal_gpio_pinconfig(WEBBLE_LED2_PIN, WEBBLE_LED2_CFG);

#if WEBBLE_LEDS_ACTIVE_LOW
    am_hal_gpio_state_write(WEBBLE_LED0_PIN, AM_HAL_GPIO_OUTPUT_SET);
    am_hal_gpio_state_write(WEBBLE_LED1_PIN, AM_HAL_GPIO_OUTPUT_SET);
    am_hal_gpio_state_write(WEBBLE_LED2_PIN, AM_HAL_GPIO_OUTPUT_SET);
#else
    am_hal_gpio_state_write(WEBBLE_LED0_PIN, AM_HAL_GPIO_OUTPUT_CLEAR);
    am_hal_gpio_state_write(WEBBLE_LED1_PIN, AM_HAL_GPIO_OUTPUT_CLEAR);
    am_hal_gpio_state_write(WEBBLE_LED2_PIN, AM_HAL_GPIO_OUTPUT_CLEAR);
#endif

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
    int status;

    webble_stage(WEBBLE_STAGE_RADIO_TASK);
    nsx_printf("webble: RadioTask start, initializing service\r\n");
    status = webble_service_init();
    if (status != NS_STATUS_SUCCESS) {
        webble_fail(g_webble_stage, status);
    }
    nsx_printf("webble: service started, advertising as '%s'\r\n", WEBBLE_ADV_NAME);
    webble_stage(WEBBLE_STAGE_WSF_DISPATCH);
    while (1) {
        g_radio_stack_min_words = uxTaskGetStackHighWaterMark(NULL);
        wsfOsDispatcher();
    }
}

static void setup_task(void *pvParameters) {
    (void)pvParameters;
    webble_stage(WEBBLE_STAGE_BLE_PRE_INIT);
    webble_ble_interrupts_init();
    ns_ble_pre_init(); /* legacy compatibility hook; app owns interrupt policy */
    webble_stage(WEBBLE_STAGE_CREATE_RADIO);
    if (xTaskCreate(RadioTask, "RadioTask", WEBBLE_RADIO_STACK_WORDS, NULL,
                    WEBBLE_RADIO_TASK_PRIORITY, &radio_task_handle) != pdPASS) {
        webble_fail(WEBBLE_STAGE_CREATE_RADIO, NS_STATUS_FAILURE);
    }
    g_setup_stack_min_words = uxTaskGetStackHighWaterMark(NULL);
    vTaskSuspend(NULL);
    while (1) {
        ;
    }
}

int main(void) {
    nsx_core_config_t cfg = {.api = &nsx_core_V1_0_0};
    int status;

    g_webble_stage = WEBBLE_STAGE_CORE_INIT;
    status = nsx_core_init(&cfg);
    if (status != NS_STATUS_SUCCESS) {
        webble_fail(WEBBLE_STAGE_CORE_INIT, status);
    }

    /* Baseline board power-up before touching the radio. App-owned: explicit
     * calls rather than pulling the whole power/timer/interrupt module chain.
     * The BLE controller manages its own power/reset inside HciDrvRadioBoot().
     *
     * Mirrors legacy neuralSPOT's ns_development_default bring-up
     * (bNeedSharedSRAM=true path): am_bsp_low_power_init() alone only does
     * am_hal_pwrctrl_low_power_init() + SIMOBUCK enable on this board — it does
     * NOT configure DAXI or the cache. Apollo4 Cooper's HciDrvRadioBoot()
     * uploads a large firmware image out of flash, so a properly configured
     * cache/DAXI matters for that transfer's timing and reliability. */
    webble_stage(WEBBLE_STAGE_BOARD_POWER);
    am_bsp_low_power_init();

#if defined(AM_PART_APOLLO4P)
    webble_stage(WEBBLE_STAGE_DAXI);
    am_hal_daxi_config_t daxi_cfg = {
        .bDaxiPassThrough = false,
        .bAgingSEnabled = false,
        .eAgingCounter = AM_HAL_DAXI_CONFIG_AGING_1024,
        .eNumBuf = AM_HAL_DAXI_CONFIG_NUMBUF_32,
        .eNumFreeBuf = AM_HAL_DAXI_CONFIG_NUMFREEBUF_3,
    };
    status = am_hal_daxi_config(&daxi_cfg);
    if (status != AM_HAL_STATUS_SUCCESS) {
        webble_fail(WEBBLE_STAGE_DAXI, status);
    }
#endif

#if defined(AM_PART_APOLLO3P) || defined(AM_PART_APOLLO3) || defined(AM_PART_APOLLO4P)
    webble_stage(WEBBLE_STAGE_CACHE);
    status = am_hal_cachectrl_config(&am_hal_cachectrl_defaults);
    if (status != AM_HAL_STATUS_SUCCESS) {
        webble_fail(WEBBLE_STAGE_CACHE, status);
    }
    status = am_hal_cachectrl_enable();
    if (status != AM_HAL_STATUS_SUCCESS) {
        webble_fail(WEBBLE_STAGE_CACHE, status);
    }
#endif

    webble_stage(WEBBLE_STAGE_ITM);
    nsx_itm_printf_enable();
    nsx_printf("webble: boot\r\n");
    nsx_interrupt_master_enable();

    webble_stage(WEBBLE_STAGE_CREATE_HEARTBEAT);
    if (xTaskCreate(heartbeat_task, "HB", WEBBLE_HEARTBEAT_STACK_WORDS, NULL,
                    WEBBLE_HEARTBEAT_TASK_PRIORITY,
                    &heartbeat_task_handle) != pdPASS) {
        webble_fail(WEBBLE_STAGE_CREATE_HEARTBEAT, NS_STATUS_FAILURE);
    }

    webble_stage(WEBBLE_STAGE_CREATE_SETUP);
    if (xTaskCreate(setup_task, "Setup", WEBBLE_SETUP_STACK_WORDS, NULL,
                    WEBBLE_RADIO_TASK_PRIORITY, &setup_task_handle) != pdPASS) {
        webble_fail(WEBBLE_STAGE_CREATE_SETUP, NS_STATUS_FAILURE);
    }
    webble_stage(WEBBLE_STAGE_SCHEDULER);
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
