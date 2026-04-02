# audio_capture

Demonstrates **nsx-audio** on the Apollo510 EVB.  Configures the PDM
microphone at 16 kHz, captures 30 ms audio frames, and prints peak
amplitude to SWO every 100 frames.

## Build & run

```bash
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .
nsx view      --app-dir .
```
