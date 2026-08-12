/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026, Ambiq */
/*
 * Placeholder model header. Replace it with your Vela-compiled model:
 *
 *   pip install ethos-u-vela
 *   vela your_model.tflite --accelerator-config ethos-u85-256 \
 *       --output-dir vela_out
 *   python tools/tflite_to_header.py vela_out/your_model_vela.tflite \
 *       src/model_data.h
 *
 * Until then the app builds and runs, but prints instructions instead of
 * running inference.
 */
#ifndef MODEL_DATA_H
#define MODEL_DATA_H
#include <cstdint>

#define MODEL_DATA_IS_PLACEHOLDER 1

alignas(16) const unsigned char g_model_data[] = { 0 };
const unsigned int g_model_data_len = 0;

#endif  // MODEL_DATA_H
