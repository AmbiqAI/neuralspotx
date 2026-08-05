# ExecuTorch add

This app runs the 728-byte `add.pte` program from ExecuTorch v1.3.0 through
the `nsx::executorch` low-level, heap-free runtime facade on Apollo510 EVB.
The `.pte` is baked into the firmware at build time. A successful run prints
`EXECUTORCH_OK output0_milli=3000`.

The development override in `nsx.yml` points to the adjacent
`/home/nmysore/nsx-executorch` checkout. Run from this directory:

```bash
uv --directory ../.. run nsx lock --app .
uv --directory ../.. run nsx sync --app .
uv --directory ../.. run nsx configure --app . --board apollo510_evb
uv --directory ../.. run nsx build --app . --board apollo510_evb
```

The ExecuTorch source and its pinned submodules are acquired before NSX sync;
configure and build do not download dependencies.
