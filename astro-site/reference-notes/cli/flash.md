J-Link Commander is discovered from `JLINK_PATH`, `PATH`, or the standard SEGGER install
locations on Linux, macOS and Windows. The resolved path is passed into CMake so discovery
is consistent across NSX operations.

Flashing uses the board-defined flash settings and requires the selected target's `.bin`
and the generated `jlink/<target>/flash_cmds.jlink` recipe. A successful process exit is
rejected unless J-Link reports an actual flash-download operation.

`--sdk-root` warns that `nsx.lock` and the SBOM no longer describe the flashed binary,
cannot be combined with `--frozen`, and forces a reconfigure when it differs from the
cached override. With `--frozen`, explicit probe selection still forces configure.

```bash
cd <app-dir>
nsx flash

# Flash another executable finalized by the same NSX/CMake project.
nsx flash --target hpx_profiler_power
```

`--app-dir` names the app directory containing `nsx.yml`; when it is omitted NSX searches
upward from the current directory. The positional `app` argument overrides `--app-dir` and
is resolved under the current directory and under `examples/`.

The out-of-tree SDK escape hatch is described under [SDK provider selection](/neuralspotx/guides/modules/sdk-providers/) in the guides.

`--target` names an executable to flash; omitting it selects the app's primary
executable.
