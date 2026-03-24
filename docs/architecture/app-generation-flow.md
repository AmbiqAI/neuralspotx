# App Generation Flow

This page shows how `nsx create-app` turns a board choice into a standalone
generated app.

```mermaid
flowchart TD
    A["nsx create-app"] --> B["Load lock registry"]
    B --> C["Resolve starter profile"]
    C --> D["Select board and SoC"]
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

The result is a single-target app that contains the vendored board and module
content needed for configure, build, flash, and SWO view.
