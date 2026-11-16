# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
cmake_minimum_required(VERSION 3.31)
include("${CMAKE_CURRENT_LIST_DIR}/debug/validate.cmake")
file(READ "${NSX_DEBUG_BUILD_DIR}/nsx-debug/context.json" context)
nsx_debug_validate("${context}" "${NSX_DEBUG_BUILD_DIR}" "${NSX_DEBUG_SOURCE_DIR}" "${NSX_DEBUG_BOARD}")
