# Adding Boards

Built-in board definitions live in `src/neuralspotx/boards/`.

## Board Responsibilities

A board definition selects:

- the SoC family
- startup and system source behavior
- linker behavior
- flash and SWO settings
- default SDK provider family and revision

## Expected Workflow

1. add the new board definition
2. update board metadata and starter profile defaults
3. verify provider compatibility
4. generate a test app for the board
5. run configure and build validation
6. update the published board coverage docs

## Important Constraint

Only add a built-in board when its startup, BSP, and provider path are coherent
enough to support generated-app builds.
