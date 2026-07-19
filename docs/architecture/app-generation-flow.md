# App Generation Flow

This page shows how `nsx create-app` turns an initial board choice into a
standalone generated app. The generated manifest starts with that board as its
active target; the app model can subsequently declare a larger supported
target set.

```mermaid
flowchart TD
    A["nsx create-app"] --> B["Load lock registry"]
    B --> C["Resolve starter profile"]
    C --> D["Select initial board and SoC"]
    D --> E["Resolve module closure"]
    E --> F["Select SDK provider and revision"]
    F --> G["Copy board into app/boards"]
    E --> H["Copy modules into app/modules"]
    A --> I["Copy cmake/nsx helpers"]
    A --> J["Write nsx.yml and CMakeLists.txt"]
    G --> K["Generated App"]
    H --> K
    I --> K
    J --> K
```

## Result

The result contains the board and module content needed for configure, build,
flash, and SWO view. App manifests may declare multiple boards under
`targets.supported`; each operation selects one active board, using
`targets.default` unless `--board` overrides it.

Module closure and lock data are target-aware. App-local vendoring remains the
build input, and separate default build directories prevent artifacts from
different boards from being mixed.
