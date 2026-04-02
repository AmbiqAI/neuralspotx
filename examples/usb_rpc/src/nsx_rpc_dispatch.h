/**
 * @file nsx_rpc_dispatch.h
 * @brief USB RPC dispatcher — decode an NsxRpcMessage and call the appropriate
 *        handler, then encode the response into the caller-supplied buffer.
 *
 * Wire framing (same on both sides):
 *   [ uint32_t LE length ] [ <length> bytes of nanopb-encoded NsxRpcMessage ]
 *
 * No dynamic memory is used anywhere in this translation unit.
 */
#ifndef NSX_RPC_DISPATCH_H
#define NSX_RPC_DISPATCH_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Maximum encoded size of any NsxRpcMessage (computed at codegen time). */
#define NSX_RPC_MAX_MSG_BYTES  280   /* 270 + small margin */

/** 4-byte little-endian length prefix that precedes every message on the wire. */
#define NSX_RPC_FRAME_HDR_LEN  4

/**
 * Decode @p rx_buf (nanopb-encoded NsxRpcMessage, @p rx_len bytes), dispatch
 * to the appropriate handler, encode the response into @p tx_buf, and write the
 * encoded length to @p *tx_len.
 *
 * @param rx_buf   Incoming encoded message (after the 4-byte length prefix).
 * @param rx_len   Number of bytes in @p rx_buf.
 * @param tx_buf   Caller-supplied response buffer (at least NSX_RPC_MAX_MSG_BYTES).
 * @param tx_len   Out: number of bytes written to @p tx_buf.
 *
 * @return true if the message was decoded and a response was produced;
 *         false on decode error (tx_len set to 0).
 */
bool nsx_rpc_dispatch(const uint8_t *rx_buf, uint32_t rx_len,
                      uint8_t *tx_buf, uint32_t *tx_len);

/**
 * Write a 4-byte little-endian length prefix to @p hdr_buf.
 * @p hdr_buf must point to at least 4 bytes.
 */
static inline void nsx_rpc_write_hdr(uint8_t *hdr_buf, uint32_t len) {
    hdr_buf[0] = (uint8_t)(len);
    hdr_buf[1] = (uint8_t)(len >> 8);
    hdr_buf[2] = (uint8_t)(len >> 16);
    hdr_buf[3] = (uint8_t)(len >> 24);
}

/**
 * Read a 4-byte little-endian length prefix from @p hdr_buf.
 */
static inline uint32_t nsx_rpc_read_hdr(const uint8_t *hdr_buf) {
    return (uint32_t)hdr_buf[0]
         | ((uint32_t)hdr_buf[1] << 8)
         | ((uint32_t)hdr_buf[2] << 16)
         | ((uint32_t)hdr_buf[3] << 24);
}

#ifdef __cplusplus
}
#endif

#endif /* NSX_RPC_DISPATCH_H */
