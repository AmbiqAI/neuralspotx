# usb_serial

Demonstrates **nsx-usb** on the Apollo510 family.  Opens a USB CDC serial
port and echoes any received data back to the host.

This is also a **multi-target** example that exercises additive
`requires:`. A single lean `nsx.yml` declares a `targets:` block
supporting both `apollo510_evb` (default) and `apollo510b_evb`, and layers
the TinyUSB serial stack (`nsx-ambiq-usb`, `nsx-usb`) plus its
`nsx-timer` / `nsx-interrupt` dependencies on top of each board's derived
`<board>_minimal` profile via a top-level `requires:` list. Both boards
share one combined `nsx.lock`.

## Build & Flash

```bash
# Default board (apollo510_evb)
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .

# Sibling board
nsx build     --app-dir . --board apollo510b_evb
```

## Connecting

After flashing, a USB CDC device appears on the host.  Connect with any
serial terminal:

**macOS / Linux:**

```bash
# pyserial (recommended — handles DTR automatically)
python3 -c "
import serial, time
ser = serial.Serial('/dev/cu.usbmodem14301', 115200, timeout=1)
ser.dtr = True    # required: device checks DTR for connected state
time.sleep(0.3)
ser.write(b'Hello Apollo!\n')
print(ser.readline())
ser.close()
"

# or use screen
screen /dev/cu.usbmodem14301 115200

# or minicom
minicom -D /dev/cu.usbmodem14301 -b 115200
```

**Windows:**

```powershell
# Check Device Manager for COMx port number
# Use PuTTY, TeraTerm, or pyserial with the COM port
python -c "import serial; s=serial.Serial('COM3',115200); s.dtr=True; s.write(b'test\n'); print(s.readline()); s.close()"
```

> **pyserial note:** You must set `ser.dtr = True` before the device
> reports as connected.  Without DTR, the device ignores incoming data.

> **Pick the right port:** a J-Link probe also exposes its own virtual
> COM port, so you may see two `/dev/cu.usbmodem*` devices. The NSX CDC
> device enumerates with VID/PID `0xCafe`/`0x4011` — connect to that one,
> not the J-Link VCP. List ports with
> `python3 -m serial.tools.list_ports -v` to confirm which is which.

## Expected Behavior

Everything you type (or send) is echoed back character-by-character:

```
$ screen /dev/cu.usbmodem14301 115200
Hello!        ← you type this
Hello!        ← device echoes it back
test 123
test 123
```

Meanwhile SWO output (via `nsx view`) shows:

```
USB CDC echo ready — connect a serial terminal
```

## How It Works

The firmware is minimal — ~20 lines of application code:

1. Initialize `nsx_usb` with static TX/RX buffers (placed in SRAM for DMA)
2. Poll `nsx_usb_connected()` until a host opens the CDC port
3. Non-blocking read into a 256-byte echo buffer
4. Immediately send back whatever was received

USB DMA buffers use `NSX_MEM_SRAM_BSS` placement because the DMA engine
on Apollo5 cannot access TCM.
