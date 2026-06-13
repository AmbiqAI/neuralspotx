#include <string.h>
#include "nsx_core.h"
#include "nsx_mem.h"
#include "nsx_usb.h"

#define USB_TX_BUF_SIZE  2048
#define USB_RX_BUF_SIZE  1024   /* >= NSX_USB_MIN_CDC_RX_BUFSIZE */
#define ECHO_BUF_SIZE    256

/* USB DMA buffers — place in SRAM for DMA engine access. */
static NSX_MEM_SRAM_BSS uint8_t g_usb_tx_buf[USB_TX_BUF_SIZE];
static NSX_MEM_SRAM_BSS uint8_t g_usb_rx_buf[USB_RX_BUF_SIZE];
static uint8_t g_echo_buf[ECHO_BUF_SIZE];
static bool g_logged_connected = false;

int main(void)
{
    nsx_core_config_t core_cfg = {
        .api = &nsx_core_V1_0_0,
    };
    (void)nsx_core_init(&core_cfg);

    nsx_itm_printf_enable();
    nsx_cache_enable();

    nsx_usb_config_t usb = {
        .tx_buffer       = g_usb_tx_buf,
        .tx_buffer_len   = sizeof(g_usb_tx_buf),
        .rx_buffer       = g_usb_rx_buf,
        .rx_buffer_len   = sizeof(g_usb_rx_buf),
        .poll_interval_us = NSX_USB_DEFAULT_POLL_US,
        .timeout_ms       = NSX_USB_DEFAULT_TIMEOUT_MS,
        .rx_cb            = NULL,
        .vendor_rx_cb     = NULL,
        .device_desc      = NULL,
        .user_ctx         = NULL,
    };

    if (nsx_usb_init(&usb) != 0) {
        nsx_printf("USB init failed\r\n");
        while (1) {}
    }

    nsx_printf("USB CDC echo ready — connect a serial terminal\r\n");

    while (1) {
        if (!nsx_usb_connected(&usb)) {
            g_logged_connected = false;
            nsx_delay_us(100000);
            continue;
        }

        if (!g_logged_connected) {
            g_logged_connected = true;
        }

        uint32_t n = 0;
        nsx_usb_read_nb(&usb, g_echo_buf, sizeof(g_echo_buf), &n);
        if (n > 0) {
            uint32_t sent = 0;
            nsx_usb_send(&usb, g_echo_buf, n, &sent);
        }
    }
}
