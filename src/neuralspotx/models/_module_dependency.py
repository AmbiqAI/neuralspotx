"""Required module dependency declarations (module metadata versions, not Git refs)."""

from __future__ import annotations

from dataclasses import dataclass

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from ..bsp_contracts import BspRequirement, contract_versions


@dataclass(frozen=True, slots=True)
class ModuleDependency:
    """A required module and optional PEP 440 constraint on its metadata version."""

    name: str
    version: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"name": self.name, "version": self.version}

    def __str__(self) -> str:
        return f"{self.name} ({self.version})" if self.version else self.name


def parse_required_dependencies(
    entries: list[object], context: str
) -> list[ModuleDependency | BspRequirement]:
    """Validate authoring syntax; preserve dependency order and bare names."""
    result: list[ModuleDependency | BspRequirement] = []
    for index, entry in enumerate(entries):
        where = f"{context}.depends.required[{index}]"
        if isinstance(entry, dict) and "role" in entry:
            if set(entry) != {"role", "contracts"} or entry["role"] != "bsp":
                raise ValueError(f"{where}: role requirements must contain role: bsp and contracts")
            result.append(
                BspRequirement(contract_versions(entry["contracts"], f"{where}.contracts"))
            )
            continue
        version = None
        if isinstance(entry, str):
            name = entry
        elif isinstance(entry, dict):
            if set(entry) - {"name", "version"}:
                raise ValueError(f"{where}: only name and version are allowed")
            name = entry.get("name")
            if "version" in entry:
                version = entry["version"]
                if not isinstance(version, str) or not version.strip():
                    raise ValueError(f"{where}.version must be a nonempty PEP 440 constraint")
                try:
                    spec = SpecifierSet(version)
                    if not spec:
                        raise InvalidSpecifier("constraint must contain at least one comparison")
                    if any(item.operator == "===" for item in spec):
                        raise InvalidSpecifier("arbitrary equality is unsupported")
                except InvalidSpecifier as exc:
                    raise ValueError(
                        f"{where}: invalid version constraint {version!r}: {exc}"
                    ) from exc
        else:
            raise ValueError(f"{where} must be string module name or mapping with name/version")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{where}.name must be a nonempty string")
        result.append(ModuleDependency(name, version))
    return result
