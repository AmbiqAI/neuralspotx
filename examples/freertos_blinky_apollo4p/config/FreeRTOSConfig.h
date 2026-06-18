/*
 * SPDX-License-Identifier: MIT
 *
 * nsx-freertos Phase 1 reference FreeRTOSConfig.h template.
 *
 * COPY this file into your application (as FreeRTOSConfig.h) and tune it.
 * FreeRTOSConfig.h values are APPLICATION policy: neither nsx-freertos nor the
 * core SDK own heap size, task topology, stack sizes, priorities, or tick rate.
 *
 * Target profile for this template:
 *   - SoC:        staged Cortex-M55 or Cortex-M4F boards
 *   - Port:       generic upstream ARM_CM55_NTZ (non-TrustZone) or ARM_CM4F
 *   - Tick:       plain SysTick (tickless idle disabled)
 *   - Heap:       heap_4 (configTOTAL_HEAP_SIZE below)
 *
 * Handler binding: ARM_CM55_NTZ provides strong SVC_Handler / PendSV_Handler /
 * SysTick_Handler symbols directly. ARM_CM4F uses strong nsx-freertos shim
 * handlers that route those vectors to FreeRTOS' vPortSVCHandler /
 * xPortPendSVHandler / xPortSysTickHandler symbols. Do NOT remap or redefine
 * those handlers in the application.
 *
 * See https://www.FreeRTOS.org/a00110.html for the full option reference.
 */
#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

#include <stdint.h>

extern uint32_t SystemCoreClock;

/* Shared generic Cortex-M port configuration. ARMv8-M-only knobs below are
 * harmless when the selected port is ARM_CM4F and keep one shared template. */
#define configENABLE_TRUSTZONE                          0
#define configRUN_FREERTOS_SECURE_ONLY                  1
#define configENABLE_MPU                                0
#define configENABLE_FPU                                1
#define configENABLE_MVE                                1
#define configTOTAL_MPU_REGIONS                         16

/* Scheduler behaviour. */
#define configUSE_PREEMPTION                            1
#define configUSE_TIME_SLICING                          1
#define configUSE_PORT_OPTIMISED_TASK_SELECTION         0
#define configMAX_PRIORITIES                            ( 8 )
#define configIDLE_SHOULD_YIELD                         1
#define configUSE_16_BIT_TICKS                          0

/* Clocking and memory (application policy). */
#define configCPU_CLOCK_HZ                              ( SystemCoreClock )
#define configTICK_RATE_HZ                              ( ( TickType_t ) 1000 )
#define configMINIMAL_STACK_SIZE                        ( ( uint16_t ) 256 )
#define configMINIMAL_SECURE_STACK_SIZE                 ( 1024 )
#define configMAX_TASK_NAME_LEN                         ( 16 )
#define configTOTAL_HEAP_SIZE                           ( ( size_t ) ( 32 * 1024 ) )

/* Phase 1 uses a plain SysTick tick; tickless idle is disabled. */
#define configUSE_TICKLESS_IDLE                         0

/* Feature selection. */
#define configUSE_MUTEXES                               1
#define configUSE_RECURSIVE_MUTEXES                     1
#define configUSE_COUNTING_SEMAPHORES                   1
#define configUSE_TASK_NOTIFICATIONS                    1
#define configUSE_QUEUE_SETS                            0
#define configUSE_TRACE_FACILITY                        0
#define configQUEUE_REGISTRY_SIZE                       0
#define configUSE_NEWLIB_REENTRANT                      0

/* Hook functions. */
#define configUSE_IDLE_HOOK                             0
#define configUSE_TICK_HOOK                             0
#define configUSE_MALLOC_FAILED_HOOK                    1
#define configCHECK_FOR_STACK_OVERFLOW                  2

/* Memory allocation scheme. */
#define configSUPPORT_STATIC_ALLOCATION                 0
#define configSUPPORT_DYNAMIC_ALLOCATION                1

/* Software timers. */
#define configUSE_TIMERS                                1
#define configTIMER_TASK_PRIORITY                       ( 3 )
#define configTIMER_QUEUE_LENGTH                         5
#define configTIMER_TASK_STACK_DEPTH                    ( configMINIMAL_STACK_SIZE )

/* Assert. */
#define configASSERT( x )  if( ( x ) == 0 ) { taskDISABLE_INTERRUPTS(); for( ;; ); }

/* Indirect handler routing. The ARM_CM4F port exposes vPortSVCHandler /
 * xPortPendSVHandler / xPortSysTickHandler rather than the SVC_Handler /
 * PendSV_Handler / SysTick_Handler vector names owned by NSX startup, so
 * nsx-freertos installs strong shim handlers that branch to the port entry
 * points. Disable the direct-installation check accordingly. */
#define configCHECK_HANDLER_INSTALLATION                0

/* Interrupt priority configuration. */
#ifdef __NVIC_PRIO_BITS
    #define configPRIO_BITS                             __NVIC_PRIO_BITS
#elif defined(ARMCM4)
    #define configPRIO_BITS                             3
#else
    #define configPRIO_BITS                             4
#endif
#define configLIBRARY_LOWEST_INTERRUPT_PRIORITY         ( ( 1U << configPRIO_BITS ) - 1U )
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY    3
#define configKERNEL_INTERRUPT_PRIORITY \
    ( configLIBRARY_LOWEST_INTERRUPT_PRIORITY << ( 8 - configPRIO_BITS ) )
#define configMAX_SYSCALL_INTERRUPT_PRIORITY \
    ( configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY << ( 8 - configPRIO_BITS ) )

/* Optional API inclusion. */
#define INCLUDE_vTaskPrioritySet                        1
#define INCLUDE_uxTaskPriorityGet                       1
#define INCLUDE_vTaskDelete                             1
#define INCLUDE_vTaskSuspend                            1
#define INCLUDE_vTaskDelayUntil                         1
#define INCLUDE_vTaskDelay                              1
#define INCLUDE_xTaskGetSchedulerState                  1
#define INCLUDE_xTaskGetCurrentTaskHandle               1
#define INCLUDE_uxTaskGetStackHighWaterMark             1
#define INCLUDE_xTaskGetIdleTaskHandle                  1
#define INCLUDE_eTaskGetState                           1
#define INCLUDE_xTimerPendFunctionCall                  1

#endif /* FREERTOS_CONFIG_H */
