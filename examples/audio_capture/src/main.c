#include <string.h>
#include "nsx_core.h"
#include "nsx_system.h"
#include "nsx_mem.h"
#include "nsx_audio.h"

#define SAMPLE_RATE 16000
#define NUM_CHANNELS 1
#define NUM_SAMPLES 480 /* 30 ms at 16 kHz */

/* DMA buffer must be in SRAM (DMA engine cannot access TCM on Apollo5). */
static NSX_MEM_SRAM_BSS uint32_t
    __attribute__((aligned(32))) g_dma_buf[NUM_SAMPLES * NUM_CHANNELS * 2];

static int16_t g_pcm_buf[NUM_SAMPLES * NUM_CHANNELS];

static volatile uint32_t g_frame_count;
static volatile uint8_t g_frame_ready;

static void audio_cb(nsx_audio_config_t *cfg, void *buffer, uint32_t num_samples) {
    (void)cfg;
    (void)buffer;
    (void)num_samples;
    g_frame_count++;
    g_frame_ready = 1;
}

int main(void) {
    const nsx_system_config_t system_cfg = {
        .perf_mode = NSX_PERF_LOW,
        .enable_cache = true,
        .debug = {.transport = NSX_DEBUG_ITM},
    };
    uint32_t status = nsx_system_init(&system_cfg);
    if (status != 0) {
        /* Hardware/debug setup may have failed before printf became available. */
        while (1) {
        }
    }
    nsx_printf("Audio system initialized\r\n");

    nsx_audio_config_t audio = {
        .source = NSX_AUDIO_SOURCE_PDM,
        .num_channels = NUM_CHANNELS,
        .num_samples = NUM_SAMPLES,
        .pdm = nsx_audio_pdm_default,
        .dma_buffer = g_dma_buf,
        .dma_buffer_size = sizeof(g_dma_buf),
        .pcm_buffer = g_pcm_buf,
        .pcm_buffer_size = sizeof(g_pcm_buf),
        .callback = audio_cb,
        .user_ctx = NULL,
    };

    status = nsx_audio_init(&audio);
    if (status != 0) {
        nsx_printf("Audio init failed: %lu\r\n", (unsigned long)status);
        while (1) {
        }
    }
    nsx_interrupt_master_enable();
    status = nsx_audio_start(&audio);
    if (status != 0) {
        nsx_printf("Audio start failed: %lu\r\n", (unsigned long)status);
        while (1) {
        }
    }

    nsx_printf("Audio capture started: %u Hz, %u ch, %u samples/frame\r\n", SAMPLE_RATE,
               NUM_CHANNELS, NUM_SAMPLES);

    while (1) {
        if (g_frame_ready) {
            g_frame_ready = 0;

            /* Compute simple peak amplitude for the frame. */
            int16_t peak = 0;
            for (uint32_t i = 0; i < NUM_SAMPLES; ++i) {
                int16_t v = g_pcm_buf[i];
                if (v < 0)
                    v = -v;
                if (v > peak)
                    peak = v;
            }

            if ((g_frame_count % 100) == 0) {
                nsx_printf("Frame %lu  peak=%d\r\n", (unsigned long)g_frame_count, (int)peak);
            }
        }
    }
}
