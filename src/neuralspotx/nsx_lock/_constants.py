"""Module-level constants for ``nsx.lock`` schema and hashing.

Split out so the kind/model/IO/hashing submodules can each import only
the constants they need without pulling in the rest of the package.
"""

from __future__ import annotations

LOCK_FILENAME = "nsx.lock"
LOCK_SCHEMA_VERSION = 4

# Schema version of the on-disk ``git-artifact-hashes-vN.json`` user cache.
# This versions both the layout and the hashing semantics: v2 includes
# recursively hydrated git submodules in artifact hashes.
_ARTIFACT_HASH_CACHE_SCHEMA_VERSION = 2

# Files/dirs to exclude when hashing a vendored module tree.
# Local-source mirrors should ignore developer-only environment/cache
# directories so ``nsx lock`` and ``nsx sync --frozen`` remain stable.
_HASH_EXCLUDE_DIRS = frozenset(
	{".git", "__pycache__", ".pytest_cache", ".DS_Store", ".venv", "venv"}
)

# Auto-generated overlays written into ``app_dir/cmake/nsx/`` by
# ``_write_app_module_file`` after ``_copy_packaged_tree``. These files
# are not part of the packaged ``nsx-tooling`` wheel resource and must
# be excluded when hashing the materialized tree, otherwise every app
# produces a different content hash purely because of its own
# ``NSX_APP_MODULES`` list.
NSX_TOOLING_AUTOGEN_FILES = frozenset({"modules.cmake"})
