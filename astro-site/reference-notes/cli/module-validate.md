Run this before registering a custom module to catch errors early.

```bash
nsx module validate path/to/nsx-module.yaml
nsx module validate path/to/nsx-module.yaml --json
```

The checks are that `schema_version` is `1`, that `module.name`, `module.type` and
`module.version` are present and valid, that `module.type` is one of the supported types,
that `support.ambiqsuite` is `true`, that `build.cmake.package` and `build.cmake.targets`
are present and non-empty, that `depends.required` and `depends.optional` are present, and
that `compatibility.boards`, `compatibility.socs` and `compatibility.toolchains` are
non-empty.
