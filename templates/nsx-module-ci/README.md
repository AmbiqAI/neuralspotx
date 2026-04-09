# NSX Module CI/Release Template

Drop these files into any `nsx-*` module repo to get:

1. **CI** (`.github/workflows/ci.yml`) — runs on every push/PR
   - Advisory clang-format check (won't block, just warns)
   - Validates `nsx-module.yaml` version is valid semver

2. **Release** (`.github/workflows/release.yml`) — automated releases
   - **release-please** watches `main` for [Conventional Commits](https://www.conventionalcommits.org/)
   - On merge of the release PR: creates a GitHub release with a source tarball

3. **release-please config** — controls versioning behavior
   - Pre-1.0: breaking changes bump minor (`0.1.0` → `0.2.0`)
   - Post-1.0: breaking changes bump major (`1.0.0` → `2.0.0`)
   - Version is written to `nsx-module.yaml` `module.version` field

## Setup for a new module

1. Copy `ci.yml` and `release.yml` into `.github/workflows/`
2. Copy `.clang-format` to the repo root
3. Copy `release-please-config.json` and edit `package-name` to your module name
4. Copy `.release-please-manifest.json` and set the current version
5. Commit with a `chore:` prefix

## Commit message conventions

Release-please uses [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Version bump (pre-1.0) | Version bump (post-1.0) |
|--------|----------------------|------------------------|
| `fix:` | patch (0.1.0 → 0.1.1) | patch |
| `feat:` | patch (0.1.0 → 0.1.1) | minor |
| `feat!:` or `BREAKING CHANGE:` | minor (0.1.0 → 0.2.0) | major |
| `refactor:` | patch | patch |
| `docs:`, `chore:`, `test:` | no release | no release |

## Files to copy

```
.github/workflows/ci.yml
.github/workflows/release.yml
.clang-format
release-please-config.json        # edit package-name
.release-please-manifest.json     # set current version
```
