# Adding Modules

NSX modules are separate repos with `nsx-module.yaml` and a CMake surface.

## Expected Workflow

1. create or prepare the module repo
2. define `nsx-module.yaml`
3. expose the correct CMake targets
4. declare required dependencies
5. declare board, SoC, and toolchain compatibility
6. add the module to the curated registry if it should be part of the standard catalog
7. test it through app generation or `nsx module add`

## Design Rules

- keep compatibility explicit
- keep dependency closure clean
- avoid pass-through wrapper modules unless they provide a real stable surface
- prefer wrapper-based SDK consumption over copying arbitrary low-level SDK code
