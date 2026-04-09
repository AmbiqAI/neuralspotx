/******************************************************************************
 *
 * linker_script_itcm.ld - Hybrid ITCM/MRAM variant for CoreMark power benchmark.
 *
 * CoreMark hot-path objects (~9.5 KB) execute from ITCM (zero-wait-state SRAM).
 * HAL, NSX runtime, and libc stay in MRAM and execute via I-cache.
 * ITCM content is stored in MRAM and copied at startup by the CRT.
 *
 *****************************************************************************/
ENTRY(Reset_Handler)

MEMORY
{
    MCU_ITCM     (rwx) : ORIGIN = 0x00000000, LENGTH = 262144
    MCU_MRAM     (rx)  : ORIGIN = 0x00410000, LENGTH = 4128768
    MCU_TCM      (rwx) : ORIGIN = 0x20000000, LENGTH = 507904
    SHARED_SRAM  (rwx) : ORIGIN = 0x20080000, LENGTH = 3145728
}

SECTIONS
{
    /* ISR vector and patch table — must be in MRAM for SBL boot */
    .text :
    {
        . = ALIGN(4);
        KEEP(*(.isr_vector));
        KEEP(*(.patch));
        . = ALIGN(4);
        _etext = .;
    } > MCU_MRAM

    /* Only CoreMark hot-path objects execute from ITCM.
     * Everything else (HAL, NSX runtime, libc) stays in MRAM via I-cache.
     * CoreMark objects total ~9.5 KB — fits easily in 32K ITCM. */
    .itcm_text :
    {
        . = ALIGN(4);
        _s_itcm_text = .;
        *(.itcm_text)
        *(.itcm_text*)
        *core_main*(.text .text* .rodata .rodata*)
        *core_list_join*(.text .text* .rodata .rodata*)
        *core_matrix*(.text .text* .rodata .rodata*)
        *core_state*(.text .text* .rodata .rodata*)
        *core_util*(.text .text* .rodata .rodata*)
        . = ALIGN(4);
        _e_itcm_text = .;
    } > MCU_ITCM AT>MCU_MRAM

    /* Everything else executes from MRAM (via I-cache) */
    .text_mram :
    {
        . = ALIGN(4);
        *(.text)
        *(.text*)
        *(.rodata)
        *(.rodata*)
        . = ALIGN(4);
    } > MCU_MRAM

    .ARM.extab :
    {
        *(.ARM.extab* .gnu.linkonce.armextab.*)
    } > MCU_MRAM

    __exidx_start = .;
    .ARM.exidx :
    {
        *(.ARM.exidx* .gnu.linkonce.armexidx.*)
    } > MCU_MRAM
    __exidx_end = .;

    .preinit_array :
    {
        PROVIDE_HIDDEN (__preinit_array_start = .);
        KEEP (*(.preinit_array*))
        PROVIDE_HIDDEN (__preinit_array_end = .);
    } > MCU_MRAM

    .init_array :
    {
        PROVIDE_HIDDEN (__init_array_start = .);
        KEEP (*(SORT(.init_array.*)))
        KEEP (*(.init_array*))
        PROVIDE_HIDDEN (__init_array_end = .);
    } > MCU_MRAM

    .fini_array :
    {
        PROVIDE_HIDDEN (__fini_array_start = .);
        KEEP (*(SORT(.fini_array.*)))
        KEEP (*(.fini_array*))
        PROVIDE_HIDDEN (__fini_array_end = .);
    } > MCU_MRAM

    /* Used by startup CRT to copy ITCM content from MRAM */
    _init_itcm_text = LOADADDR(.itcm_text);

    /* User stack section initialized by startup code. */
    .stack (NOLOAD):
    {
        . = ALIGN(8);
        *(.stack)
        *(.stack*)
        . = ALIGN(8);
    } > MCU_TCM

    .heap (NOLOAD):
    {
        __heap_start__ = .;
        end = __heap_start__;
        _end = end;
        __end = end;
        KEEP(*(.heap))
        __heap_end__ = .;
        __HeapLimit = __heap_end__;
    }  > MCU_TCM

    .data :
    {
        . = ALIGN(4);
        _sdata = .;
        *(.data)
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } > MCU_TCM AT>MCU_MRAM

    /* used by startup to initialize data */
    _init_data = LOADADDR(.data);

    .bss :
    {
        . = ALIGN(4);
        _sbss = .;
        *(.bss)
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > MCU_TCM

    ASSERT( _ebss <= ORIGIN(MCU_TCM) + LENGTH(MCU_TCM),
            "TCM overflow: stack+heap+data+bss exceed MCU_TCM" )

    ASSERT( _e_itcm_text <= 0x00008000,
            "ITCM overflow: CoreMark hot path exceeds 32 KB ITCM" )

    .sram_bss (NOLOAD):
    {
        . = ALIGN(4);
        _ssram_bss = .;
        *(.sram_bss)
        *(.sram_bss*)
        . = ALIGN(4);
        _esram_bss = .;
    } > SHARED_SRAM

    .shared :
    {
        . = ALIGN(4);
        KEEP(*(.resource_table))
        . = ALIGN(4);

        _ssdata = .;
        KEEP(*(.shared))
        *(.shared*)
        . = ALIGN(4);
        _sedata = .;
    } > SHARED_SRAM AT>MCU_MRAM
    _init_data_sram = LOADADDR(.shared);

    .ARM.attributes 0 : { *(.ARM.attributes) }
}
