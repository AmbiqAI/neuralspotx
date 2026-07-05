# BLE Webble

Minimal BLE peripheral example for NSX BLE targets.

> **Status:** Experimental. The BLE modules and this example have been
> hardware-smoke-tested on AP3, AP4, and AP510B, but the modules are still
> being integrated into the normal NSX registry flow and the example currently
> uses local module paths.

The app demonstrates the optional `nsx-cordio` + `nsx-ble` modules with all
application policy kept in the app: board power/cache bring-up, FreeRTOS task
sizes, WSF buffer pool sizing, LED heartbeat, advertised service contents, and
TX-power selection.

## BLE in this example

Bluetooth LE peripherals advertise a small amount of data so a central device
(phone, laptop, or test script) can find them. After a central connects, it uses
GATT services and characteristics to read values, write values, or subscribe to
notifications.

`ble_webble` keeps that model intentionally small:

- one primary custom service;
- one read-only heartbeat characteristic;
- one notify characteristic that increments while subscribed;
- one read/write RGB value;
- standard GAP name and Device Information Service fields.

The example is meant to show the NSX/Cordio wiring and a clean app-owned policy
boundary, not to be a full BLE framework. Pairing/bonding policy, multiple
services, production advertising strategy, and application-specific protocol
design should stay in the application.

## Targets

- Default board: `apollo4p_blue_kxr_evb`
- Supported boards:
  - `apollo3p_evb`
  - `apollo4p_blue_kxr_evb`
  - `apollo510b_evb`
- Toolchains build-validated:
  - `gcc`

Before promoting this from experimental to a normal registry-backed example,
replace the local `nsx-ble`/`nsx-cordio` module paths with registry/git module
constraints.

## Build

```bash
nsx build
nsx build --board apollo3p_evb
nsx build --board apollo510b_evb
```

## Host demo

A small Python smoke tool is available at:

- `tools/ble_webble_host.py`

Examples:

```bash
python -m py_compile tools/ble_webble_host.py
python tools/ble_webble_host.py --list
python tools/ble_webble_host.py --name NSX-AP5 --notify-seconds 3 --rgb 102030
```

When multiple matching boards are advertising, re-run with `--address` to
target the intended device explicitly.

## Flash

When multiple probes are attached, always specify the intended J-Link serial.
For the local Linux tower used during bring-up:

```bash
nsx flash --board apollo4p_blue_kxr_evb --probe-serial 1160001350
```

## BLE service

Advertised names:

| Board | Name |
| --- | --- |
| Apollo3 Blue Plus | `NSX-AP3` |
| Apollo4 Blue Plus | `NSX-AP4` |
| Apollo510B EVB | `NSX-AP5` |

Primary service UUID:

```text
19b10000-0000-537e-4f6c-d104768a1214
```

Characteristics:

| UUID suffix | Properties | Payload |
| --- | --- | --- |
| `2001` | Read | 1-byte unsigned heartbeat counter, updated by the LED task |
| `5001` | Read + notify | 1-byte unsigned notify counter, updated while subscribed |
| `8001` | Read + write | 3-byte RGB value |

The app also populates the standard Device Information Service with Ambiq and
board-specific values, requests a larger MTU/data length where supported, and
registers an event callback for connect/disconnect, MTU, data-length, CCC, and
hardware-error diagnostics.

## Liveness

The heartbeat task toggles board LEDs every 500 ms, prints `webble: heartbeat N`
over SWO, and mirrors the low byte of `N` into the readable `2001`
characteristic.

## Hardware smoke coverage

Validated manually:

| Board | Address observed | Checks |
| --- | --- | --- |
| Apollo3 Blue Plus | `8E:29:64:00:45:31` | GAP name, DIS, service discovery, heartbeat read |
| Apollo4 Blue Plus | `B8:57:B3:37:C0:3C` | GAP name, DIS, service discovery, heartbeat read, notify values |
| Apollo510B EVB | `00:20:50:42:40:90` | GAP name, DIS, service discovery, heartbeat read, connection/data-length/CCC logs |
