# hello_world

Minimal **nsx** application. Initialises the runtime core and prints a
message to SWO in a loop.

This is the recommended starting point for new users — it validates that
your toolchain, board connection, and SWO viewer are all working.

It is also a **multi-target** example: a single lean `nsx.yml` declares a
`targets:` block supporting both `apollo510_evb` (default) and
`apollo4p_blue_kxr_evb`. Each board resolves its own derived
`<board>_minimal` profile and commits its own `nsx.<board>.lock`, so this
serves as the simplest cross-family proving ground (Apollo5 + Apollo4P).

## Build & Run

```bash
# Default board (apollo510_evb)
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .      # requires JLink + EVB
nsx view      --app-dir .      # opens SWO viewer

# Apollo4P Blue KXR EVB
nsx build     --app-dir . --board apollo4p_blue_kxr_evb
```

## Expected Output

The SWO viewer will print:

```
Hello from nsx! (0)
Hello from nsx! (1)
Hello from nsx! (2)
...
```

Messages repeat once per second.  If you see nothing, check:

1. Board is powered and connected via SWD (JLink)
2. `nsx flash` completed without errors
3. SWO pin is not remapped — the default EVB configuration works out of the box
