#include <string.h>

#include "ns_core.h"
#include "ns_ambiqsuite_harness.h"
#include "nsx_mem.h"
#include "nsx_usb.h"
#include "nsx_rpc_dispatch.h"

/* ------------------------------------------------------------------ */
/* Buffers — all static, no malloc                                     */
/* ------------------------------------------------------------------ */

#define USB_TX_BUF_SIZE  2048
#define USB_RX_BUF_SIZE  2048   /* >= NSX_USB_MIN_CDC_RX_BUFSIZE (1024) */

/* USB DMA buffers — place in SRAM for DMA engine access. */
static NSX_MEM_SRAM_BSS uint8_t g_usb_tx_buf[USB_TX_BUF_SIZE];
static NSX_MEM_SRAM_BSS uint8_t g_usb_rx_buf[USB_RX_BUF_SIZE];

/* One frame in + one frame out; sized for the largest possible message. */
static uint8_t g_rx_frame[NSX_RPC_MAX_MSG_BYTES];
static uint8_t g_tx_frame[NSX_RPC_MAX_MSG_BYTES];
static uint8_t g_hdr_buf[NSX_RPC_FRAME_HDR_LEN];

/* ------------------------------------------------------------------ */
/* Frame receive state machine                                         */
/* ------------------------------------------------------------------ */

typedef enum {
    RX_WAIT_HDR,   /* collecting the 4-byte length prefix */
    RX_WAIT_BODY,  /* collecting the protobuf payload     */
} rx_state_t;

static rx_state_t g_rx_state    = RX_WAIT_HDR;
static uint32_t   g_rx_need     = NSX_RPC_FRAME_HDR_LEN;
static uint32_t   g_rx_got      = 0;
static uint32_t   g_rx_body_len = 0;

/**
 * Feed bytes from the CDC FIFO into the framing state machine.
 * Returns true + sets *frame_len when a complete message payload has been
 * received into g_rx_frame.
 */
static bool rx_feed(nsx_usb_config_t *usb, uint32_t *frame_len) {
    while (nsx_usb_data_available(usb)) {
        uint8_t *dst;
        uint32_t room;

        if (g_rx_state == RX_WAIT_HDR) {
            dst  = g_hdr_buf + g_rx_got;
            room = (uint32_t)sizeof(g_hdr_buf) - g_rx_got;
        } else {
            dst  = g_rx_frame + g_rx_got;
            room = g_rx_body_len - g_rx_got;
        }

        uint32_t n = 0;
        nsx_usb_read_nb(usb, dst, room, &n);
        if (n == 0) {
            break;
        }
        g_rx_got += n;

        if (g_rx_state == RX_WAIT_HDR && g_rx_got == NSX_RPC_FRAME_HDR_LEN) {
            /* Decode length. */
            uint32_t len = nsx_rpc_read_hdr(g_hdr_buf);
            if (len == 0 || len > NSX_RPC_MAX_MSG_BYTES) {
                ns_printf("RPC framing: bad length %u — resync\r\n", (unsigned)len);
                g_rx_state = RX_WAIT_HDR;
                g_rx_got   = 0;
                continue;
            }
            g_rx_body_len = len;
            g_rx_state    = RX_WAIT_BODY;
            g_rx_got      = 0;
        } else if (g_rx_state == RX_WAIT_BODY && g_rx_got == g_rx_body_len) {
            /* Complete payload received. */
            *frame_len    = g_rx_body_len;
            g_rx_state    = RX_WAIT_HDR;
            g_rx_got      = 0;
            g_rx_body_len = 0;
            return true;
        }
    }
    return false;
}

/* ------------------------------------------------------------------ */
/* Main                                                                */
/* ------------------------------------------------------------------ */

int main(void) {
    ns_core_config_t core_cfg = {
        .api = &ns_core_V1_0_0,
    };
    (void)ns_core_init(&core_cfg);
    ns_itm_printf_enable();
    nsx_cache_enable();

    nsx_usb_config_t usb = {
        .tx_buffer        = g_usb_tx_buf,
        .tx_buffer_len    = sizeof(g_usb_tx_buf),
        .rx_buffer        = g_usb_rx_buf,
        .rx_buffer_len    = sizeof(g_usb_rx_buf),
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

    ns_printf("NSX USB RPC ready\r\n");
    ns_printf("Protocol: 4-byte LE length prefix + nanopb NsxRpcMessage\r\n");

    while (1) {
        if (!nsx_usb_connected(&usb)) {
            /* Not connected — reset framing state to avoid stale half-frames. */
            g_rx_state    = RX_WAIT_HDR;
            g_rx_got      = 0;
            g_rx_body_len = 0;
            ns_delay_us(100000);
            continue;
        }

        uint32_t frame_len = 0;
        if (!rx_feed(&usb, &frame_len)) {
            /* No complete frame yet — yield. */
            ns_delay_us(100);
            continue;
        }

        /* Dispatch and encode response. */
        uint32_t tx_payload_len = 0;
        bool ok = nsx_rpc_dispatch(g_rx_frame, frame_len,
                                   g_tx_frame, &tx_payload_len);
        if (!ok || tx_payload_len == 0) {
            continue;
        }

        /* Send: length header then payload. */
        nsx_rpc_write_hdr(g_hdr_buf, tx_payload_len);
        uint32_t sent = 0;
        nsx_usb_send(&usb, g_hdr_buf, NSX_RPC_FRAME_HDR_LEN, &sent);
        nsx_usb_send(&usb, g_tx_frame, tx_payload_len, &sent);
    }
}
