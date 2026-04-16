# audio_capture

Demonstrates **nsx-audio** on the Apollo510 EVB.  Configures the PDM
microphone at 16 kHz, captures 30 ms audio frames, and prints peak
amplitude to SWO every 100 frames (~3 seconds).

## Build & Run

```bash
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .      # requires EVB with onboard PDM mic
nsx view      --app-dir .      # opens SWO viewer
```

## Expected Output

The SWO viewer will print once at startup, then peak amplitude every
100 frames (~3 s at 16 kHz / 480 samples per frame):

```
Audio capture started: 16000 Hz, 1 ch, 480 samples/frame
Frame 100  peak=1842
Frame 200  peak=2105
Frame 300  peak=947
Frame 400  peak=3210
```

Peak values depend on ambient noise.  Silence gives values near 0;
speaking near the mic gives values in the thousands (int16 range).

## How It Works

1. Configures the PDM peripheral at 16 kHz mono via `nsx_audio_init()`
2. DMA transfers 480-sample (30 ms) frames into a ping-pong buffer
3. A callback fires per frame; the main loop computes peak amplitude
4. DMA buffers use `NSX_MEM_SRAM_BSS` placement — the DMA engine on
   Apollo5 cannot access TCM

## Hardware Notes

- The Apollo510 EVB has an onboard PDM MEMS microphone
- No additional hardware or wiring is needed
- PDM clock and data pins are set by the EVB board definition
