/**
 * @file nsx_rpc_dispatch.c
 * @brief USB RPC dispatcher implementation.
 *
 * Statically allocated — no malloc, no dynamic buffers.
 *
 * Handler stubs:
 *   PING    — echo sequence number, report uptime
 *   INFER   — toy classifier: sums input bytes, divides into N_CLASSES
 *   STATUS  — report firmware version, free estimate, board name
 */

#include "nsx_rpc_dispatch.h"
#include "nsx_rpc.pb.h"

#include "pb_decode.h"
#include "pb_encode.h"

#include "am_mcu_apollo.h"  /* am_hal_timer_count64 for uptime */
#include "ns_core.h"        /* ns_printf */

/* Shorthand aliases for nanopb-generated enum values. */
#define NSX_MSG_PING_REQ     NsxRpcMsgType_NSX_MSG_PING_REQ
#define NSX_MSG_PING_RESP    NsxRpcMsgType_NSX_MSG_PING_RESP
#define NSX_MSG_INFER_REQ    NsxRpcMsgType_NSX_MSG_INFER_REQ
#define NSX_MSG_INFER_RESP   NsxRpcMsgType_NSX_MSG_INFER_RESP
#define NSX_MSG_STATUS_REQ   NsxRpcMsgType_NSX_MSG_STATUS_REQ
#define NSX_MSG_STATUS_RESP  NsxRpcMsgType_NSX_MSG_STATUS_RESP

/* ------------------------------------------------------------------ */
/* Configuration                                                       */
/* ------------------------------------------------------------------ */

#ifndef NSX_RPC_FIRMWARE_VERSION
#define NSX_RPC_FIRMWARE_VERSION  0x00010000u   /* 1.0.0 */
#endif

#ifndef NSX_RPC_BOARD_NAME
#define NSX_RPC_BOARD_NAME  "apollo510_evb"
#endif

#define NSX_RPC_N_CLASSES   5   /* toy inference stub: 5 output classes */

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

/** Coarse uptime in milliseconds derived from STIMER. */
static uint32_t get_uptime_ms(void) {
    /* am_hal_stimer_counter_get() returns raw 3 MHz ticks on Apollo5. */
    return am_hal_stimer_counter_get() / 3000;
}

/* ------------------------------------------------------------------ */
/* Handlers                                                            */
/* ------------------------------------------------------------------ */

static void handle_ping(const NsxPingRequest *req, NsxRpcMessage *resp) {
    resp->type = NSX_MSG_PING_RESP;
    resp->which_payload = NsxRpcMessage_ping_resp_tag;
    resp->payload.ping_resp.seq       = req->seq;
    resp->payload.ping_resp.uptime_ms = get_uptime_ms();
}

static void handle_infer(const NsxInferRequest *req, NsxRpcMessage *resp) {
    /* Toy classifier: sum input bytes, map to class. */
    uint32_t sum = 0;
    for (uint16_t i = 0; i < req->input.size; i++) {
        sum += req->input.bytes[i];
    }
    uint32_t class_id = sum % NSX_RPC_N_CLASSES;

    static const char *labels[NSX_RPC_N_CLASSES] = {
        "idle", "walk", "run", "gesture", "unknown"
    };

    const char *label = labels[class_id];
    float       conf  = 0.5f + (float)(sum & 0x3F) / 256.0f;  /* 0.5–0.75 range */

    resp->type = NSX_MSG_INFER_RESP;
    resp->which_payload = NsxRpcMessage_infer_resp_tag;
    resp->payload.infer_resp.model_id   = req->model_id;
    resp->payload.infer_resp.class_id   = class_id;
    resp->payload.infer_resp.confidence = conf;

    /* Copy label into the fixed-size bytes field. */
    uint16_t llen = 0;
    while (label[llen] && llen < sizeof(resp->payload.infer_resp.label.bytes) - 1) {
        llen++;
    }
    resp->payload.infer_resp.label.size = llen;
    __builtin_memcpy(resp->payload.infer_resp.label.bytes, label, llen);
}

static void handle_status(NsxRpcMessage *resp) {
    resp->type = NSX_MSG_STATUS_RESP;
    resp->which_payload = NsxRpcMessage_status_resp_tag;
    resp->payload.status_resp.firmware_version = NSX_RPC_FIRMWARE_VERSION;
    resp->payload.status_resp.free_heap_bytes  = 0;  /* not tracked in demo */

    const char *name = NSX_RPC_BOARD_NAME;
    uint16_t nlen = 0;
    while (name[nlen] && nlen < sizeof(resp->payload.status_resp.board_name.bytes) - 1) {
        nlen++;
    }
    resp->payload.status_resp.board_name.size = nlen;
    __builtin_memcpy(resp->payload.status_resp.board_name.bytes, name, nlen);
}

/* ------------------------------------------------------------------ */
/* Public dispatch entry point                                         */
/* ------------------------------------------------------------------ */

bool nsx_rpc_dispatch(const uint8_t *rx_buf, uint32_t rx_len,
                      uint8_t *tx_buf, uint32_t *tx_len) {
    *tx_len = 0;

    /* Decode incoming message. */
    NsxRpcMessage req = NsxRpcMessage_init_default;
    pb_istream_t  in  = pb_istream_from_buffer(rx_buf, rx_len);
    if (!pb_decode(&in, NsxRpcMessage_fields, &req)) {
        ns_printf("RPC: decode error: %s\r\n", PB_GET_ERROR(&in));
        return false;
    }

    /* Build response. */
    NsxRpcMessage resp = NsxRpcMessage_init_default;

    switch (req.type) {
        case NSX_MSG_PING_REQ:
            handle_ping(&req.payload.ping_req, &resp);
            break;
        case NSX_MSG_INFER_REQ:
            handle_infer(&req.payload.infer_req, &resp);
            break;
        case NSX_MSG_STATUS_REQ:
            handle_status(&resp);
            break;
        default:
            ns_printf("RPC: unknown msg type %d\r\n", (int)req.type);
            return false;
    }

    /* Encode response. */
    pb_ostream_t out = pb_ostream_from_buffer(tx_buf, NSX_RPC_MAX_MSG_BYTES);
    if (!pb_encode(&out, NsxRpcMessage_fields, &resp)) {
        ns_printf("RPC: encode error: %s\r\n", PB_GET_ERROR(&out));
        return false;
    }

    *tx_len = (uint32_t)out.bytes_written;
    return true;
}
