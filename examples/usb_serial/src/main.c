#include <string.h>
#include "ns_core.h"
#include "ns_ambiqsuite_harness.h"
#include "nsx_usb.h"

#define USB_TX_BUF_SIZE  2048
#define USB_RX_BUF_SIZE  1024   /* >= NSX_USB_MIN_CDC_RX_BUFSIZE */
#define ECHO_BUF_SIZE    256

static uint8_t g_usb_tx_buf[USB_TX_BUF_SIZE];
static uint8_t g_usb_rx_buf[USB_RX_BUF_SIZE];
static uint8_t g_echo_buf[ECHO_BUF_SIZE];

int main(void)
{
    ns_core_config_t core_cfg = {
        .api = &ns_core_V1_0_0,
    };
    (void)ns_core_init(&core_cfg);

    ns_itm_printf_enable();

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
        ns_printf("USB init failed\r\n");
        while (1) {}
    }

    ns_printf("USB CDC echo ready — connect a serial terminal\r\n");

    while (1) {
        if (!nsx_usb_connected(&usb)) {
            ns_delay_us(100000);
            continue;
        }

        uint32_t n = 0;
        nsx_usb_read_nb(&usb, g_echo_buf, sizeof(g_echo_buf), &n);
        if (n > 0) {
            uint32_t sent = 0;
            nsx_usb_send(&usb, g_echo_buf, n, &sent);
        }
    }
}
