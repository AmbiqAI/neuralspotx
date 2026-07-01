# BLE Webble

Minimal Apollo4 Blue Plus BLE peripheral example for NSX.

The app demonstrates the optional `nsx-cordio` + `nsx-ble` modules with all
application policy kept in the app: board power/cache bring-up, FreeRTOS task
sizes, WSF buffer pool sizing, LED heartbeat, advertised service contents, and
TX-power selection.

## Target

- Board: `apollo4p_blue_kxr_evb`
- SoC: Apollo4p / Cooper BLE controller
- Toolchains build-validated:
  - `gcc`
  - `atfe`
  - `armclang` / ACFE

## Build

```bash
nsx build
nsx build --toolchain atfe --build-dir build-atfe
nsx build --toolchain armclang --build-dir build-armclang
```

## Flash

When multiple probes are attached, always specify the intended J-Link serial.
For the local Linux tower used during bring-up:

```bash
nsx flash --probe-serial 1160001350
```

## BLE service

Advertised name:

```text
Webble
```

Primary service UUID:

```text
19b10000-0000-537e-4f6c-d104768a1214
```

Characteristics:

| UUID suffix | Properties | Payload |
| --- | --- | --- |
| `2001` | Read | 1-byte unsigned heartbeat counter, updated by the LED task |
| `5001` | Read + notify | 1-byte unsigned notify counter |
| `8001` | Read + write | 3-byte RGB value |

The app sets Cooper TX power to `TX_POWER_LEVEL_PLUS_4P0_dBm` before starting
the BLE service.

## Liveness

The heartbeat task toggles the Apollo4 Blue Plus LEDs every 500 ms, prints
`webble: heartbeat N` over SWO, and mirrors the low byte of `N` into the
readable `2001` characteristic.
