Use this to register an external module for one app without editing the packaged registry,
for local filesystem modules and custom git repos that are not part of the built-in NSX
catalog. `register` writes an app-local override into `nsx.yml` and then vendors the
registered module into that app.

Local filesystem example:

```bash
cd <app-dir>
nsx module register my-custom-module \
    --metadata /path/to/my-custom-module/nsx-module.yaml \
    --project my_custom_repo \
    --project-local-path /path/to/my-custom-module
```

Git-backed example:

```bash
cd <app-dir>
nsx module register my-custom-module \
    --metadata /path/to/my-custom-module/nsx-module.yaml \
    --project my_custom_repo \
    --project-url https://github.com/myorg/my_custom_repo.git \
    --project-revision main \
    --project-path modules/my_custom_repo
```
