# npu_person_detect — Ethos-U85 Person Detection Example

TFLite Micro person-detection inference offloaded to the Arm Ethos-U85 NPU
on the atomiq110 FPGA turbo board, demonstrating:

- **nsx-npu** NPU power-up + Ethos-U core-driver init (`nsx_npu_init`)
- **heliaRT ethos-u custom op** dispatch (`NSX_HELIA_RT_ENABLE_ETHOSU=ON`)
- **Vela** offline model compilation for `ethos-u85-256`
- **ITM/SWO** printf output with scores and DWT cycle timing

## Model

Google Visual Wake Words person_detect (int8), compiled offline with
[Vela](https://pypi.org/project/ethos-u-vela/):

```bash
pip install ethos-u-vela
vela person_detect.tflite \
    --accelerator-config ethos-u85-256 \
    --output-dir vela_out
```

- Input: `[1, 96, 96, 1]` int8, output: `[1, 2]` int8 (no-person / person)
- All 44 ops compile into a **single `ethos-u` custom op** (100% NPU offload)
- `--accelerator-config ethos-u85-256` matches the 256-MAC Ethos-U85
  configuration on atomiq110

The compiled model is committed as `src/person_detect_model_data.h`. To swap
models, re-run Vela and regenerate the header (xxd-style C array, 16-byte
aligned).

## How the pieces fit

| Layer | Role |
| --- | --- |
| Vela (offline) | Compiles the TFLite graph into an Ethos-U command stream wrapped in an `ethos-u` custom op |
| heliaRT (`nsx-helia-rt`) | TFLM runtime; its ethos-u kernel is compiled against the real driver when `NSX_HELIA_RT_ENABLE_ETHOSU=ON` (see this app's `CMakeLists.txt`) |
| `nsx-npu` | Powers the NPU domain, initializes the Ethos-U core driver, wires `am_npu_isr` → `ethosu_irq_handler` |
| This app | Registers `AddEthosU()` in the op resolver and invokes the interpreter |

## Build

```bash
cd neuralspotx/examples/npu_person_detect
nsx lock      --app-dir .
nsx configure --app-dir .
nsx build     --app-dir .
```

## Flash & View Output

```bash
nsx flash --app-dir .
nsx view  --app-dir .   # SWO viewer; atomiq110 FPGA turbo runs at 48 MHz
```

Expected output (NPU-enabled target):

```
person_detect on atomiq110 Ethos-U85 (TFLM + Vela)
Model: 242848 bytes (ethos-u85-256, 100% NPU offload)
Ethos-U85 driver initialized.
...
[zeros   ] ... no-person=... person=... -> no-person
```

On an FPGA image whose bitstream generation does not match the SDK payload
(or has no Ethos-U85), initialization fails with an actionable message:

```
person_detect on atomiq110 Ethos-U85 (TFLM + Vela)
Model: 242848 bytes (ethos-u85-256, 100% NPU offload)
ERROR: nsx_npu_init failed (rc=...).
Ethos-U85 init failed. On FPGA builds make sure the loaded bitstream
generation matches the SDK payload and includes a working Ethos-U85; ...
```

## Hardware notes

- The app requests HP perf mode; `am_hal_pwrctrl_npu_mode_select()` works on
  both silicon and the NPU-enabled FPGA image. Set `skip_perf_mode = true`
  in `nsx_npu_config_t` only to bypass mode selection on a custom
  pre-silicon target.
- The FPGA bitstream and the packaged SDK payload must come from the same
  SDK generation: the NPU-era bitstream moves CRM to a new base address and
  decodes the Ethos-U85 at 0x400E0000. A mismatch bus-faults or fails init.
- The Vela model *requires* the NPU — there is no CPU fallback for the
  `ethos-u` custom op. For a CPU/CMSIS-NN baseline, run the original
  (non-Vela) model with the same harness.
