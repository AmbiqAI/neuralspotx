By default `nsx view` chooses the board-appropriate reset policy. Most boards start the
viewer first and then run the app's normal SEGGER reset target once. Apollo4 secure boards
attach without resetting, because SEGGER's Apollo4 reset flow halts in the secure boot
handoff and can make the SWO viewer exit.

```bash
cd <app-dir>
nsx view
```

The viewer requires SEGGER SWO tooling in `PATH` and depends on the target being configured
for SWO output. Apollo4 secure boards are validated with `nsx flash` followed by an
attach-only `nsx view`. Apollo510 keeps the normal viewer-first `Reset` flow and does not
require a stronger reset mode.

`--app-dir` names the app directory containing `nsx.yml`; when it is omitted NSX searches
upward from the current directory. The positional `app` argument overrides `--app-dir` and
is resolved under the current directory and under `examples/`.

The out-of-tree SDK escape hatch is described under [SDK provider selection](/neuralspotx/guides/modules/sdk-providers/) in the guides.
