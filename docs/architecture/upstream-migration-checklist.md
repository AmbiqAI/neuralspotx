# Upstream Migration Checklist (From Temporary Split Mode)

## 1) Repository publication

- Create remote repo for each module/board/tooling boundary.
- Push current in-place history from nested local repos.

## 2) Registry updates

- Update registry project URLs/revisions to remote repos.
- Keep module names and metadata paths stable where possible.

## 3) Manifest updates

- Update starter profile project mappings.
- Validate `west update` for AP3/AP510 profiles.

## 4) SDK provider handoff

- Confirm sdk provider repos carry required minimal payload.
- Keep `NSX_AMBIQSUITE_R*_ROOT` override behavior documented.

## 5) Validation

- `uv run nsx --help`
- `uv run nsx create-app ...`
- AP3 and AP510 build regressions pass.

## 6) Cleanup

- Remove `local-repos-deprecated` when no longer needed.
- Remove temporary migration notes from README once remote flow is primary.
