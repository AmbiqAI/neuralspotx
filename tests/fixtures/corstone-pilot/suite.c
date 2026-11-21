/* SPDX-License-Identifier: BSD-3-Clause */
#include <stdint.h>
#include "unity.h"
#include "pilot.h"

/* Exercise the startup copy/zero tables as well as the arithmetic. */
static volatile int8_t left[] = {-3, 2, 5};
static volatile int32_t accumulator;

void setUp(void) {}
void tearDown(void) {}

static void test_signed_dot_product(void) {
    const int8_t right[] = {4, 7, 1};
    TEST_ASSERT_EQUAL_INT32(0, accumulator);
    for (unsigned i = 0; i < sizeof(left) / sizeof(left[0]); ++i) {
        accumulator += left[i] * right[i];
    }
#ifdef PILOT_INJECT_FAILURE
    TEST_ASSERT_EQUAL_INT32(8, accumulator);
#else
    TEST_ASSERT_EQUAL_INT32(7, accumulator);
#endif
}

int main(void) {
    if (pilot_console_init() != 0) {
        return 2;
    }
    UnityPrint("NSX pilot hello");
    UNITY_PRINT_EOL();
    UNITY_BEGIN();
    RUN_TEST(test_signed_dot_product);
    return UNITY_END();
}
