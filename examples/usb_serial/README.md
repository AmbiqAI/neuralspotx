# usb_serial

Demonstrates **nsx-usb** on the Apollo510 EVB.  Opens a USB CDC serial
port and echoes any received data back to the host.

## Build & run

```bash
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .
```

Connect a serial terminal (e.g. `minicom`, `screen`, or `pyserial`)
to the CDC port that appears after flashing.

> **pyserial note:** You must set `ser.dtr = True` before the device
> reports as connected.
