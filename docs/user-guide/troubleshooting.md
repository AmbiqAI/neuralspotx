# Troubleshooting

This page covers common NSX problems and where to look first.

## `nsx build` fails during configure

Check:

- the selected board in `nsx.yml`
- that the vendored board exists under `app/boards/`
- that the needed modules exist under `app/modules/`

## `nsx module add` rejects a module

Likely causes:

- board incompatibility
- SoC incompatibility
- toolchain incompatibility
- missing required dependency closure

## `nsx flash` cannot program the board

Check:

- `JLinkExe` is available in `PATH`
- the board is connected and powered
- the selected board matches the hardware target

## `nsx view` shows no output

Check:

- the app was actually flashed
- the app prints through the expected SWO path
- the board-specific SWO settings match the target

The Apollo510 smoke app is a good baseline because it prints periodically.

## The app structure looks wrong

Regenerate or inspect:

- `nsx.yml`
- `app/modules/`
- `app/boards/`
- `app/cmake/nsx/`

If those are inconsistent, re-run module update or regenerate the app from a
clean workspace.
