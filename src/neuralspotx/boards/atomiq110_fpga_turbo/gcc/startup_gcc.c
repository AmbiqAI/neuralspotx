//*****************************************************************************
//
//! @file startup_gcc.c
//!
//! @brief Definitions for the Atomiq110 vector table, interrupt handlers,
//! and stack.
//
//*****************************************************************************

//*****************************************************************************
//
// ${copyright}
//
// This is part of revision ${version} of the AmbiqSuite Development Package.
//
//*****************************************************************************

#include "atomiq110.h"

//*****************************************************************************
//
// Forward declaration of interrupt handlers.
//
//*****************************************************************************
extern void Reset_Handler(void)                 __attribute ((naked));
extern void NMI_Handler(void)                   __attribute ((weak));
extern void HardFault_Handler(void)             __attribute ((weak));
extern void MemManage_Handler(void)             __attribute ((weak, alias ("HardFault_Handler")));
extern void BusFault_Handler(void)              __attribute ((weak, alias ("HardFault_Handler")));
extern void UsageFault_Handler(void)            __attribute ((weak, alias ("HardFault_Handler")));
extern void SecureFault_Handler(void)           __attribute ((weak, alias ("am_default_isr")));
extern void SVC_Handler(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void DebugMon_Handler(void)              __attribute ((weak, alias ("am_default_isr")));
extern void PendSV_Handler(void)                __attribute ((weak, alias ("am_default_isr")));
extern void SysTick_Handler(void)               __attribute ((weak, alias ("am_default_isr")));
extern void FloatingPoint_Handler(void)         __attribute ((weak, alias ("am_default_isr")));

extern void am_brownout_isr(void)               __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_watchdog_isr(void)        __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_rtc_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_vcomp_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_ioslave_fd0_isr(void)            __attribute ((weak, alias ("am_default_isr")));
extern void am_ioslave_fd0_acc_isr(void)        __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster0_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster1_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster2_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster3_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster4_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster5_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster6_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster7_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster8_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster9_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster10_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_iomaster11_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_uart_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_uart1_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_uart2_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_uart3_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_uart4_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_uart5_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_adc_isr(void)                    __attribute ((weak, alias ("am_default_isr")));
extern void am_mspi0_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_mspi1_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_mspi2_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_mspi3_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_i3c0_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_i3c1_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_i3c2_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_clkgen_isr(void)                 __attribute ((weak, alias ("am_default_isr")));
extern void am_crypto_isr(void)                 __attribute ((weak, alias ("am_default_isr")));
extern void am_timer00_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer01_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer02_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer03_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer04_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer05_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer06_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer07_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer08_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer09_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer10_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer11_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer12_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer13_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer14_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_timer15_isr(void)                __attribute ((weak, alias ("am_default_isr")));
// #### INTERNAL BEGIN ####
// CAYNSWS-3235 Deprecate the generic timer IRQ and ISR
//extern void am_timer_isr(void)                __attribute ((weak, alias ("am_default_isr")));
// #### INTERNAL END ####
extern void am_stimer_cmpr0_isr(void)           __attribute ((weak, alias ("am_default_isr")));
extern void am_stimer_cmpr1_isr(void)           __attribute ((weak, alias ("am_default_isr")));
extern void am_stimer_cmpr2_isr(void)           __attribute ((weak, alias ("am_default_isr")));
extern void am_stimer_cmpr3_isr(void)           __attribute ((weak, alias ("am_default_isr")));
extern void am_stimer_cmpr4_isr(void)           __attribute ((weak, alias ("am_default_isr")));
extern void am_stimer_cmpr5_isr(void)           __attribute ((weak, alias ("am_default_isr")));
extern void am_stimer_cmpr6_isr(void)           __attribute ((weak, alias ("am_default_isr")));
extern void am_stimer_cmpr7_isr(void)           __attribute ((weak, alias ("am_default_isr")));
extern void am_stimerof_isr(void)               __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_timer00_isr(void)         __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_timer01_isr(void)         __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_timer02_isr(void)         __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_timer03_isr(void)         __attribute ((weak, alias ("am_default_isr")));
// #### INTERNAL BEGIN ####
// CAYNSWS-3235 Deprecate the generic timer IRQ and ISR
//extern void am_secure_timer_isr(void)         __attribute ((weak, alias ("am_default_isr")));
// #### INTERNAL END ####
extern void am_secure_stimer_cmpr0_isr(void)    __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_stimer_cmpr1_isr(void)    __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_stimer_cmpr2_isr(void)    __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_stimer_cmpr3_isr(void)    __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_stimer_cmpr4_isr(void)    __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_stimer_cmpr5_isr(void)    __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_stimer_cmpr6_isr(void)    __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_stimer_cmpr7_isr(void)    __attribute ((weak, alias ("am_default_isr")));
extern void am_secure_stimerof_isr(void)        __attribute ((weak, alias ("am_default_isr")));
extern void am_watchdog_isr(void)               __attribute ((weak, alias ("am_default_isr")));
extern void am_rtc_isr(void)                    __attribute ((weak, alias ("am_default_isr")));
extern void am_i2s0_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_i2s1_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_i2s2_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_pdm0_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_pdm1_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_pdm2_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_pdm3_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_sdio0_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_sdio1_isr(void)                  __attribute ((weak, alias ("am_default_isr")));
extern void am_otp_isr(void)                    __attribute ((weak, alias ("am_default_isr")));
extern void am_usb_isr(void)                    __attribute ((weak, alias ("am_default_isr")));
extern void am_gpu_isr(void)                    __attribute ((weak, alias ("am_default_isr")));
extern void am_disp_isr(void)                   __attribute ((weak, alias ("am_default_isr")));
extern void am_dsi_isr(void)                    __attribute ((weak, alias ("am_default_isr")));
extern void am_ioslave_fd1_isr(void)            __attribute ((weak, alias ("am_default_isr")));
extern void am_ioslave_fd1_acc_isr(void)        __attribute ((weak, alias ("am_default_isr")));
extern void am_xspislv_accerr_isr(void)         __attribute ((weak, alias ("am_default_isr")));
extern void am_dme_ch0_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_dme_ch1_isr(void)                __attribute ((weak, alias ("am_default_isr")));
extern void am_npu_isr(void)                    __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio0_001f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio0_203f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio0_405f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio0_607f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio0_809f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio0_a0bf_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio0_c0df_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio0_e0ff_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio1_001f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio1_203f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio1_405f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio1_607f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio1_809f_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio1_a0bf_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio1_c0df_isr(void)             __attribute ((weak, alias ("am_default_isr")));
extern void am_gpio1_e0ff_isr(void)             __attribute ((weak, alias ("am_default_isr")));
//extern void am_software0_isr(void)              __attribute ((weak, alias ("am_default_isr")));
//extern void am_software1_isr(void)              __attribute ((weak, alias ("am_default_isr")));
//extern void am_software2_isr(void)              __attribute ((weak, alias ("am_default_isr")));
//extern void am_software3_isr(void)              __attribute ((weak, alias ("am_default_isr")));
extern void am_default_isr(void)                __attribute ((weak));

//*****************************************************************************
//
// The entry point for the application.
//
//*****************************************************************************
extern int main(void);

//*****************************************************************************
//
// Reserve space for the system stack.
//
//*****************************************************************************
__attribute__ ((section(".stack")))
static uint32_t g_pui32Stack[1024];

__attribute__ ((section(".heap"))) __attribute__ ((__used__))
static uint32_t g_pui32Heap[0];

#define AM_STACK_SIZE   (sizeof(g_pui32Stack))
#define AM_STACK_LIMIT  ((uint32_t)&g_pui32Stack)
#define AM_HEAP_SIZE    (sizeof(g_pui32Heap))

//*****************************************************************************
//
// The vector table.
//
// Proper alignment of the vector table is dependent on the number of
// external (peripheral) interrupts, see the following table for proper
// vectorbaseaddress alignment.
//     0-16      32-word
//    17-48      64-word
//    49-112    128-word
//   113-240    256-word  (Atomiq110)
//
// The Atomiq110 vector table must be located on a 1024 byte boundary.
// Maximum IRQ is 143, so the vector table has 144 entries (0-143).
//
// Note: Aliasing and weakly exporting am_mpufault_isr, am_busfault_isr, and
// am_usagefault_isr does not work if am_fault_isr is defined externally.
// Therefore, we'll explicitly use am_fault_isr in the table for those vectors.
//
//*****************************************************************************
__attribute__ ((section(".isr_vector")))
void (* const __Vectors[])(void) =
{
    (void (*)(void))((uint32_t)g_pui32Stack + sizeof(g_pui32Stack)),
                                            // The initial stack pointer
    Reset_Handler,                          // The reset handler
    NMI_Handler,                            // The NMI handler
    HardFault_Handler,                      // The hard fault handler
    MemManage_Handler,                      // The MemManage_Handler
    BusFault_Handler,                       // The BusFault_Handler
    UsageFault_Handler,                     // The UsageFault_Handler
    SecureFault_Handler,                    // The Secure Fault Handler
    0,                                      // Reserved
    0,                                      // Reserved
    0,                                      // Reserved
    SVC_Handler,                            // SVCall handler
    DebugMon_Handler,                       // Debug monitor handler
    0,                                      // Reserved
    PendSV_Handler,                         // The PendSV handler
    SysTick_Handler,                        // The SysTick handler

    //
    // Peripheral Interrupts
    //
    am_brownout_isr,                        //   0: Brownout (rstgen)
    am_secure_watchdog_isr,                 //   1: Secure Watchdog (WDT)
    am_secure_rtc_isr,                      //   2: Secure RTC
    am_vcomp_isr,                           //   3: Voltage Comparator
    am_ioslave_fd0_isr,                     //   4: I/O Slave FD0
    am_ioslave_fd0_acc_isr,                 //   5: I/O Slave FD0 Access
    am_iomaster0_isr,                       //   6: I/O Master 0
    am_iomaster1_isr,                       //   7: I/O Master 1
    am_iomaster2_isr,                       //   8: I/O Master 2
    am_iomaster3_isr,                       //   9: I/O Master 3
    am_iomaster4_isr,                       //  10: I/O Master 4
    am_iomaster5_isr,                       //  11: I/O Master 5
    am_iomaster6_isr,                       //  12: I/O Master 6
    am_iomaster7_isr,                       //  13: I/O Master 7
    am_iomaster8_isr,                       //  14: I/O Master 8
    am_iomaster9_isr,                       //  15: I/O Master 9
    am_iomaster10_isr,                      //  16: I/O Master 10
    am_iomaster11_isr,                      //  17: I/O Master 11
    am_uart_isr,                            //  18: UART0
    am_uart1_isr,                           //  19: UART1
    am_uart2_isr,                           //  20: UART2
    am_uart3_isr,                           //  21: UART3
    am_uart4_isr,                           //  22: UART4
    am_uart5_isr,                           //  23: UART5
    am_adc_isr,                             //  24: ADC
    am_mspi0_isr,                           //  25: MSPI0
    am_mspi1_isr,                           //  26: MSPI1
    am_mspi2_isr,                           //  27: MSPI2
    am_mspi3_isr,                           //  28: MSPI3
    am_i3c0_isr,                            //  29: I3C0
    am_i3c1_isr,                            //  30: I3C1
    am_i3c2_isr,                            //  31: I3C2
    am_clkgen_isr,                          //  32: ClkGen
    am_crypto_isr,                          //  33: Crypto
    am_timer00_isr,                         //  34: timer0
    am_timer01_isr,                         //  35: timer1
    am_timer02_isr,                         //  36: timer2
    am_timer03_isr,                         //  37: timer3
    am_timer04_isr,                         //  38: timer4
    am_timer05_isr,                         //  39: timer5
    am_timer06_isr,                         //  40: timer6
    am_timer07_isr,                         //  41: timer7
    am_timer08_isr,                         //  42: timer8
    am_timer09_isr,                         //  43: timer9
    am_timer10_isr,                         //  44: timer10
    am_timer11_isr,                         //  45: timer11
    am_timer12_isr,                         //  46: timer12
    am_timer13_isr,                         //  47: timer13
    am_timer14_isr,                         //  48: timer14
    am_timer15_isr,                         //  49: timer15
// #### INTERNAL BEGIN ####
// CAYNSWS-3235 Deprecate the generic timer IRQ and ISR
//  am_timer_isr,                           //  50: timer
// #### INTERNAL END ####
    am_default_isr,                         //  50: Reserved
    am_stimer_cmpr0_isr,                    //  51: System Timer Compare0
    am_stimer_cmpr1_isr,                    //  52: System Timer Compare1
    am_stimer_cmpr2_isr,                    //  53: System Timer Compare2
    am_stimer_cmpr3_isr,                    //  54: System Timer Compare3
    am_stimer_cmpr4_isr,                    //  55: System Timer Compare4
    am_stimer_cmpr5_isr,                    //  56: System Timer Compare5
    am_stimer_cmpr6_isr,                    //  57: System Timer Compare6
    am_stimer_cmpr7_isr,                    //  58: System Timer Compare7
    am_stimerof_isr,                        //  59: System Timer Overflow
    am_secure_timer00_isr,                  //  60: Secure timer0
    am_secure_timer01_isr,                  //  61: Secure timer1
    am_secure_timer02_isr,                  //  62: Secure timer2
    am_secure_timer03_isr,                  //  63: Secure timer3
// #### INTERNAL BEGIN ####
// CAYNSWS-3235 Deprecate the generic timer IRQ and ISR
//  am_secure_timer_isr,                    //  64: Secure timer
// #### INTERNAL END ####
    am_default_isr,                         //  64: Reserved
    am_secure_stimer_cmpr0_isr,             //  65: Secure System Timer Compare0
    am_secure_stimer_cmpr1_isr,             //  66: Secure System Timer Compare1
    am_secure_stimer_cmpr2_isr,             //  67: Secure System Timer Compare2
    am_secure_stimer_cmpr3_isr,             //  68: Secure System Timer Compare3
    am_secure_stimer_cmpr4_isr,             //  69: Secure System Timer Compare4
    am_secure_stimer_cmpr5_isr,             //  70: Secure System Timer Compare5
    am_secure_stimer_cmpr6_isr,             //  71: Secure System Timer Compare6
    am_secure_stimer_cmpr7_isr,             //  72: Secure System Timer Compare7
    am_secure_stimerof_isr,                 //  73: Secure System Timer Overflow
    am_watchdog_isr,                        //  74: Watchdog (WDT)
    am_rtc_isr,                             //  75: RTC
    am_i2s0_isr,                            //  76: I2S0
    am_i2s1_isr,                            //  77: I2S1
    am_i2s2_isr,                            //  78: I2S2
    am_pdm0_isr,                            //  79: PDM0
    am_pdm1_isr,                            //  80: PDM1
    am_pdm2_isr,                            //  81: PDM2
    am_pdm3_isr,                            //  82: PDM3
    am_sdio0_isr,                           //  83: SDIO0
    am_sdio1_isr,                           //  84: SDIO1
    am_otp_isr,                             //  85: OTP
    am_usb_isr,                             //  86: USB
    am_gpu_isr,                             //  87: GPU
    am_disp_isr,                            //  88: DISP
    am_dsi_isr,                             //  89: DSI
    am_ioslave_fd1_isr,                     //  90: I/O Slave FD1
    am_ioslave_fd1_acc_isr,                 //  91: I/O Slave FD1 Access
    am_default_isr,                         //  92: Reserved
    am_default_isr,                         //  93: Reserved
    am_xspislv_accerr_isr,                  //  94: XSPISLVACCERR
    am_default_isr,                         //  95: Reserved
    am_default_isr,                         //  96: Reserved
    am_default_isr,                         //  97: Reserved
    am_dme_ch0_isr,                         //  98: DME CH-0 ISR
    am_dme_ch1_isr,                         //  99: DME CH-1 ISR
    am_default_isr,                         // 100: Reserved
    am_default_isr,                         // 101: Reserved
    am_default_isr,                         // 102: Reserved
    am_default_isr,                         // 103: Reserved
    am_default_isr,                         // 104: Reserved
    am_default_isr,                         // 105: Reserved
    am_default_isr,                         // 106: Reserved
    am_default_isr,                         // 107: Reserved
    am_default_isr,                         // 108: Reserved
    am_default_isr,                         // 109: Reserved
    am_default_isr,                         // 110: Reserved
    am_default_isr,                         // 111: Reserved
    am_default_isr,                         // 112: Reserved
    am_default_isr,                         // 113: Reserved
    am_default_isr,                         // 114: Reserved
    am_default_isr,                         // 115: Reserved
    am_default_isr,                         // 116: Reserved
    am_npu_isr,                             // 117: NPU
    am_gpio0_001f_isr,                      // 118: GPIO N0 pins  0-31
    am_gpio0_203f_isr,                      // 119: GPIO N0 pins 32-63
    am_gpio0_405f_isr,                      // 120: GPIO N0 pins 64-95
    am_gpio0_607f_isr,                      // 121: GPIO N0 pins 96-127
    am_gpio0_809f_isr,                      // 122: GPIO N0 pins 128-159
    am_gpio0_a0bf_isr,                      // 123: GPIO N0 pins 160-191
    am_gpio0_c0df_isr,                      // 124: GPIO N0 pins 192-223
    am_gpio0_e0ff_isr,                      // 125: GPIO N0 pins 224-255
    am_gpio1_001f_isr,                      // 126: GPIO N1 pins  0-31
    am_gpio1_203f_isr,                      // 127: GPIO N1 pins 32-63
    am_gpio1_405f_isr,                      // 128: GPIO N1 pins 64-95
    am_gpio1_607f_isr,                      // 129: GPIO N1 pins 96-127
    am_gpio1_809f_isr,                      // 130: GPIO N1 pins 128-159
    am_gpio1_a0bf_isr,                      // 131: GPIO N1 pins 160-191
    am_gpio1_c0df_isr,                      // 132: GPIO N1 pins 192-223
    am_gpio1_e0ff_isr,                      // 133: GPIO N1 pins 224-255
    am_default_isr,                         // 134: Reserved
    am_default_isr,                         // 135: Reserved
    am_default_isr,                         // 136: Reserved
    am_default_isr,                         // 137: Reserved
    am_default_isr,                         // 138: Reserved
    am_default_isr,                         // 139: Reserved
    am_default_isr,                         // 140: Reserved
    am_default_isr,                         // 141: Reserved
    FloatingPoint_Handler,                  // 142: Floating Point Exception
    am_default_isr,                         // 143: RSVD_LAST_IRQ

//  am_software0_isr,                       // xxx: SOFTWARE0
//  am_software1_isr,                       // xxx: SOFTWARE1
//  am_software2_isr,                       // xxx: SOFTWARE2
//  am_software3_isr,                       // xxx: SOFTWARE3
};

//******************************************************************************
//
// Place code immediately following vector table.
//
//******************************************************************************
//******************************************************************************
//
// The Patch table.
//
// The patch table should pad the vector table size to a total of 256 entries
// such that the code begins at 0x400.
// In other words, the final peripheral IRQ is always IRQ 143 (0-based).
//
//******************************************************************************
__attribute__ ((section(".patch")))
uint32_t const __Patchable[] =
{
                0, 0, 0, 0, 0, 0,           // 144-149
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 150-159
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 160-169
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 170-179
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 180-189
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 190-199
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 200-209
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 210-219
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 220-229
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 230-239
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,           // 240-249
    0, 0, 0, 0, 0, 0                        // 250-255
};

// define the start of the patch table - at what would be vector 144
const uint32_t  * const __pPatchable =  (uint32_t *) __Patchable;

//*****************************************************************************
//
// The following are constructs created by the linker, indicating where the
// the "data" and "bss" segments reside in memory.  The initializers for the
// "data" segment resides immediately following the "text" segment.
//
//*****************************************************************************
extern uint32_t _etext;
extern uint32_t _sdata;
extern uint32_t _edata;
extern uint32_t _sbss;
extern uint32_t _ebss;

//*****************************************************************************
//
// This is the code that gets called when the processor first starts execution
// following a reset event.  Only the absolutely necessary set is performed,
// after which the application supplied entry() routine is called.
//
//*****************************************************************************
#if defined(__GNUC_STDC_INLINE__)
void
Reset_Handler(void)
{
    //
    // Set the vector table pointer.
    //
    __asm("    ldr    r0, =0xE000ED08\n"
          "    ldr    r1, =__Vectors\n"
          "    str    r1, [r0]");

    //
    // Set the stack pointer.
    //
    __asm("    ldr    sp, [r1]");
#ifndef NOFPU
    //
    // Enable the FPU.
    //
    __asm("ldr  r0, =0xE000ED88\n"
          "ldr  r1,[r0]\n"
          "orr  r1,#(0xF << 20)\n"
          "str  r1,[r0]\n"
          "dsb\n"
          "isb\n");
#endif

    //
    // Set the stack limits
    //
    __set_MSPLIM(AM_STACK_LIMIT);
    __set_PSPLIM(AM_STACK_LIMIT);

    //
    // Copy the data segment initializers from flash to SRAM.
    //
    __asm("    ldr     r0, =_init_data\n"
          "    ldr     r1, =_sdata\n"
          "    ldr     r2, =_edata\n"
          "copy_loop:\n"
          "        ldr   r3, [r0], #4\n"
          "        str   r3, [r1], #4\n"
          "        cmp     r1, r2\n"
          "        blt     copy_loop\n");

    //
    // Copy the DTCM text from flash to DTCM.
    // This supports timing-critical routines that are placed in .dtcm_text so they execute
    // with deterministic, low-latency instruction fetch rather than depending
    // on flash/cache behavior, for example tight HAL delay loops.
    //
    __asm("    ldr     r0, =_init_dtcm_text\n"
          "    ldr     r1, =_s_dtcm_text\n"
          "    ldr     r2, =_e_dtcm_text\n"
          "copy_loop_dtcm:\n"
          "    ldr     r3, [r0], #4\n"
          "    str     r3, [r1], #4\n"
          "    cmp     r1, r2\n"
          "    blt     copy_loop_dtcm\n");

    //
    // Zero fill the bss segment.
    //
    __asm("    ldr     r0, =_sbss\n"
          "    ldr     r1, =_ebss\n"
          "    mov     r2, #0\n"
          "zero_loop:\n"
          "        cmp     r0, r1\n"
          "        it      lt\n"
          "        strlt   r2, [r0], #4\n"
          "        blt     zero_loop");

    //
    // CMSIS System Initialization
    //
    SystemInit();

    //
    // Call the application's entry point.
    //
    main();

    //
    // If main returns then execute a break point instruction
    //
    __asm("    bkpt     ");
}
#else
#error GNU STDC inline not supported.
#endif

//*****************************************************************************
//
// This is the code that gets called when the processor receives a NMI.  This
// simply enters an infinite loop, preserving the system state for examination
// by a debugger.
//
//*****************************************************************************
void
NMI_Handler(void)
{
    while(1);
}

//*****************************************************************************
//
// This is the code that gets called when the processor receives a fault
// interrupt.  This simply enters an infinite loop, preserving the system state
// for examination by a debugger.
//
//*****************************************************************************
void
HardFault_Handler(void)
{
    while(1);
}

//*****************************************************************************
//
// This is the code that gets called when the processor receives an unexpected
// interrupt.  This simply enters an infinite loop, preserving the system state
// for examination by a debugger.
//
//*****************************************************************************
void
am_default_isr(void)
{
    while(1);
}

