# hello_world

Minimal **nsx** application for the Apollo510 EVB.  Initialises the
runtime core and prints a message to SWO in a loop.

This is the recommended starting point for new users — it validates that
your toolchain, board connection, and SWO viewer are all working.

## Build & Run

```bash
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .      # requires JLink + Apollo510 EVB
nsx view      --app-dir .      # opens SWO viewer
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
