# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
# C300 CPU images fit in TCM. A linked DDR payload would turn that small
# flat binary into a padded image spanning boot memory through 0x70000000.
# Inspect the linked ELF because one project can build CPU and NPU images.
execute_process(COMMAND "${SIZE}" -A "${ELF}"
    OUTPUT_VARIABLE sections COMMAND_ERROR_IS_FATAL ANY)
if(sections MATCHES "(^|\n)[ \t]*[.]npu_model[ \t]+[1-9]")
    file(REMOVE "${BIN}")
else()
    execute_process(COMMAND "${OBJCOPY}" -Obinary "${ELF}" "${BIN}"
        COMMAND_ERROR_IS_FATAL ANY)
endif()
