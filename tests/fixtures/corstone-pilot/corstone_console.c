/* SPDX-License-Identifier: BSD-3-Clause */
#include <stdio.h>
#include "uart_stdout.h"
#include "pilot.h"

int pilot_console_init(void)
{
    UartStdOutInit();
    return 0;
}

void pilot_putchar(int ch)
{
    putchar(ch);
}
