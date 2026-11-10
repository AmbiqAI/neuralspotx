"""Strict board/provider identity recorded for each target."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..bsp_contracts import BspBinding, identifier


@dataclass(frozen=True)
class CompositionInput:
    name: str
    sha256: str

    def to_dict(self, key: str) -> dict[str, str]:
        return {key: self.name, "sha256": self.sha256}


def _inputs(value: object, key: str) -> tuple[CompositionInput, ...]:
    if not isinstance(value, list):
        raise ValueError(f"board_composition {key} inputs must be a list")
    result = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {key, "sha256"}:
            raise ValueError(f"board_composition input requires {key} and sha256")
        name = identifier(entry[key], key)
        digest = entry["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("board_composition sha256 must be 64 lowercase hex characters")
        result.append(CompositionInput(name, digest))
    if len({r.name for r in result}) != len(result):
        raise ValueError("board_composition contains duplicate input identities")
    return tuple(sorted(result, key=lambda r: r.name))


@dataclass(frozen=True)
class BoardComposition:
    board: str
    revision: str | None
    soc: str
    sdk_provider: str
    bsp: BspBinding
    descriptor_inputs: tuple[CompositionInput, ...]
    contract_inputs: tuple[CompositionInput, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "board": self.board,
            "revision": self.revision,
            "soc": self.soc,
            "sdk_provider": self.sdk_provider,
            "bsp": self.bsp.to_dict(),
            "descriptor_inputs": [r.to_dict("board") for r in self.descriptor_inputs],
            "contract_inputs": [r.to_dict("module") for r in self.contract_inputs],
        }

    @classmethod
    def parse(cls, value: object) -> BoardComposition | None:
        if value is None:
            return None
        keys = {
            "board",
            "revision",
            "soc",
            "sdk_provider",
            "bsp",
            "descriptor_inputs",
            "contract_inputs",
        }
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("Invalid board_composition; run `nsx lock` to regenerate")
        revision = value["revision"]
        if revision is not None and (not isinstance(revision, str) or not revision.strip()):
            raise ValueError("board_composition revision must be null or a nonempty string")
        return cls(
            identifier(value["board"], "board"),
            revision,
            identifier(value["soc"], "soc"),
            identifier(value["sdk_provider"], "sdk_provider"),
            BspBinding.parse(value["bsp"], "board_composition.bsp"),
            _inputs(value["descriptor_inputs"], "board"),
            _inputs(value["contract_inputs"], "module"),
        )
