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
int32_t resnet_conv_2d_9_init(
    resnet_model_context_t *ctx
);

/**
 * @brief Perform the operation
 *
 * @param[in] ctx  Context struct.
 * @param[in] input  Pointer to the input buffer.
 * @param[out] output  Pointer to the output buffer.
 *
 * @return 0 on SUCCESS
 */
int32_t resnet_conv_2d_9_run(
    resnet_model_context_t *ctx,
    const int8_t* __restrict input,
    int8_t* __restrict output
);

#ifdef __cplusplus
}
#endif