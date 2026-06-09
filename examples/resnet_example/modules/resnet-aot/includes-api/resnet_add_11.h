#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include "resnet_common.h"

/**
 * @brief Initialize the operator
 *
 * @param[in] ctx  Context struct.
 *
 * @return 0 on SUCCESS
 */
int32_t resnet_add_11_init(
    resnet_model_context_t *ctx
);

/**
 * @brief Perform the operation
 *
 * @param[in] ctx  Context struct.
 * @param[in] input1  Pointer to input1 buffer.
 * @param[in] input2  Pointer to input2 buffer.
 * @param[out] output Pointer to output buffer.
 *
 * @return 0 on SUCCESS
 */
int32_t resnet_add_11_run(
    resnet_model_context_t *ctx,
    const int8_t* __restrict input1,
    const int8_t* __restrict input2,
    int8_t* __restrict output
);

#ifdef __cplusplus
}
#endif