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

A minimal generated app is a good baseline because it prints periodically.

## The app structure looks wrong

Regenerate or inspect:

- `nsx.yml`
- `app/modules/`
- `app/boards/`
- `app/cmake/nsx/`

If those are inconsistent, re-run module update or regenerate the app from a
clean directory.

## Windows: paths too long (`MAX_PATH` exceeded)

Windows limits paths to 260 characters by default. Deep module trees under
`_nsx/` can exceed this limit, causing cryptic build or lock failures.

**Fix (per-machine, one-time):**

1. Open **Registry Editor** (`regedit`).
2. Navigate to `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem`.
3. Set `LongPathsEnabled` (DWORD) to `1`.
4. Reboot.

Alternatively, from an elevated PowerShell:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
    -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

Git also needs long-path support:

```bash
git config --global core.longpaths true
```

## Non-UTF-8 locale issues

On Linux systems with `LC_ALL=C` or other ASCII-only locales, Python may
refuse to decode module metadata files that contain non-ASCII characters.

**Fix:** Set a UTF-8 locale before running `nsx`:

```bash
export LC_ALL=C.UTF-8
```

Or set `PYTHONUTF8=1` to force Python's UTF-8 mode regardless of locale.
