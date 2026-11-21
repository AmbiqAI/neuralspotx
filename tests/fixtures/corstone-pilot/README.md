# Corstone-300 provider pilot

This opt-in Linux/GCC fixture builds one finite hello and Unity suite for
`apollo510_evb` and Arm's Cortex-M55 Corstone-300 U55 model. Apollo uses the
NSX build workflow. The Corstone branch uses plain CMake to exercise the
provider proposed in [#287](https://github.com/AmbiqAI/neuralspotx/issues/287).
First-class Corstone board selection in NSX is proposed work.

Both builds compile the same test, including reads of initialized and
zero-initialized RAM. Each board supplies a console. Arm's UART retarget also
reports the guest exit code. A failing guest assertion can still produce host
process exit zero, so the fixture checks the UART completion record.

## Build inputs

Use NSX 1.0.0, CMake 3.24 or later, Ninja, Arm GNU Toolchain, and Python 3.11
or later. Install the C300 U55 model separately under the applicable
[Arm FVP terms](https://support.arm.com/tools-and-software/fixed-virtual-platforms/iot-fvps).
Set `ARM_DEPS` to a directory containing these source checkouts. An existing
HELX C300 setup provides this layout.

| Directory | Tested source revision |
| --- | --- |
| [CMSIS_6](https://github.com/ARM-software/CMSIS_6) | `8753b993c7544f0329b2ccc61bfbc967fdb3b112` |
| [Cortex_DFP](https://github.com/ARM-software/Cortex_DFP) | `cd38dbb875f7195e70460eee51faa7ab180c24a1` |
| [ethos-u-core-platform](https://git.gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-core-platform) | `8927abdff4441e8598dbbb3f7ee03bf6bc2a8d7c` |

Set `FVP_EXE` to the installed `FVP_Corstone_SSE-300_Ethos-U55` executable.
Put your Arm GCC tools on PATH. The C300 run was tested with GCC 14.3.1.
Ordinary NSX builds and CI tests can run without the model.

## Build the shared suite

From the NSX repository root, prepare a fresh workspace. To run just the C300
case, substitute `mkdir "$work/pilot"` for the `nsx create-app` command.

```sh
work=$(mktemp -d)
nsx create-app "$work/pilot" --board apollo510_evb
cp tests/fixtures/corstone-pilot/* "$work/pilot/"
mkdir -p "$work/pilot/third_party"
git clone --depth 1 --branch v2.6.1 https://github.com/ThrowTheSwitch/Unity.git "$work/pilot/third_party/unity"
```

Cross-build the Apollo image with NSX. The pilot's acceptance criterion for
Apollo is a successful link. Hardware execution requires a separate EVB run.

```sh
nsx lock --app-dir "$work/pilot"
nsx configure --app-dir "$work/pilot" --board apollo510_evb --frozen
nsx build --app-dir "$work/pilot" --board apollo510_evb --frozen
```

Configure a separate C300 build directory and run the same source.

```sh
cmake -G Ninja -S "$work/pilot" -B "$work/c300" \
  -DNSX_BOARD=corstone300_fvp_u55 -DARM_DEPS="$ARM_DEPS"
cmake --build "$work/c300" --target pilot
python3 "$work/pilot/run.py" "$FVP_EXE" "$work/c300/pilot"
```

The guest prints `NSX pilot hello`, one passing test, and exit code 0.
To exercise the failure path, reconfigure only the C300 build.

```sh
cmake -S "$work/pilot" -B "$work/c300" -DPILOT_INJECT_FAILURE=ON
cmake --build "$work/c300" --target pilot
python3 "$work/pilot/run.py" "$FVP_EXE" "$work/c300/pilot"
```

Expect `Expected 8 Was 7`, one failed test and runner status 1. The runner
uses status 2 for a model launch error, timeout, or incomplete success record.
