This is the normal starting point for third-party and app-local modules. Validate and
register the generated module afterwards.

```bash
nsx module init my-sensor-driver

nsx module init my-sensor-driver \
    --type backend_specific \
    --summary "I2C driver for the XYZ ambient light sensor." \
    --dependency nsx-core \
    --dependency nsx-i2c \
    --soc apollo510 \
    --soc apollo510b \
    --soc apollo5b
```

The skeleton contains `nsx-module.yaml`, `CMakeLists.txt`, `README.md`,
`includes-api/<module_name>/...` and `src/<module_name>.c`.
