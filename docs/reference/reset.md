# `nsx reset`

Performs an explicit SEGGER J-Link reset. Reset is a separate mechanism and is
never added implicitly to an existing flash flow.

```text
nsx reset --device DEVICE [--probe-serial SERIAL]
          [--kind debug|swpoi] [--interface SWD] [--speed-khz 4000]
          [--verify-reconnect] [--timeout SECONDS]
```

`debug` issues the standard reset/go sequence. `swpoi` writes `0x1B` to the
Ambiq RSTGEN address `0x40000004`, which resets the target immediately and may
interrupt J-Link's write. NSX accepts only the expected interrupted-write
signature; unrelated nonzero exits remain failures.

Use `--verify-reconnect` to require a separate successful J-Link connection
after the reset. Choosing reset policy, controlling power rails, and managing
measurement synchronization remain responsibilities of the calling tool.

J-Link Commander uses the same discovery order as flashing and `nsx doctor`:
the explicit `JLINK_PATH` executable, `PATH`, then standard SEGGER install
locations on Linux, macOS, and Windows.
