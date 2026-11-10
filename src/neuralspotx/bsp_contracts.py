"""Typed BSP declarations shared by descriptors and module dependency metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass


def identifier(value: object, where: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value):
        raise ValueError(f"{where}: expected an identifier containing letters, digits, '_' or '-'")
    return value


def contract_versions(value: object, where: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value or any(type(v) is not int or v < 1 for v in value):
        raise ValueError(f"{where}: expected a nonempty list of positive integer contract versions")
    if len(set(value)) != len(value):
        raise ValueError(f"{where}: duplicate contract versions")
    return tuple(value)


@dataclass(frozen=True)
class BspBinding:
    module: str
    contract: int

    @classmethod
    def parse(cls, value: object, where: str) -> BspBinding:
        if not isinstance(value, dict) or set(value) != {"module", "contract"}:
            raise ValueError(f"{where}: expected module and contract")
        module = identifier(value["module"], f"{where}.module")
        version = value["contract"]
        if type(version) is not int or version not in (1, 2):
            raise ValueError(f"{where}.contract: expected 1 or 2")
        if version == 1 and module != "nsx-ambiq-bsp":
            raise ValueError(f"{where}: contract 1 is reserved for the built-in nsx-ambiq-bsp")
        return cls(module, version)

    def to_dict(self) -> dict[str, str | int]:
        return {"module": self.module, "contract": self.contract}


@dataclass(frozen=True)
class BspRequirement:
    contracts: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {"role": "bsp", "contracts": list(self.contracts)}


@dataclass(frozen=True)
class BspOffer:
    versions: tuple[int, ...]
    socs: tuple[str, ...]


def parse_bsp_offer(value: object, where: str) -> BspOffer | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"provides"}:
        raise ValueError(f"{where}.contracts: expected provides")
    provides = value["provides"]
    if not isinstance(provides, dict) or set(provides) != {"bsp"}:
        raise ValueError(f"{where}.contracts.provides: only bsp is supported")
    bsp = provides["bsp"]
    if not isinstance(bsp, dict) or set(bsp) != {"versions", "socs"}:
        raise ValueError(f"{where}.contracts.provides.bsp: expected versions and socs")
    versions = contract_versions(bsp["versions"], f"{where}.contracts.provides.bsp.versions")
    socs = bsp["socs"]
    if not isinstance(socs, list) or not socs:
        raise ValueError(f"{where}.contracts.provides.bsp.socs: expected explicit SoCs")
    names = tuple(identifier(s, f"{where}.contracts.provides.bsp.socs") for s in socs)
    if len(set(names)) != len(names):
        raise ValueError(f"{where}.contracts.provides.bsp.socs: duplicate SoCs")
    return BspOffer(versions, names)
