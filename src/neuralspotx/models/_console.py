"""Advisory primary-console declarations; never firmware configuration."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .._errors import NSXConfigError


@dataclass(frozen=True, slots=True)
class ConsoleConfig:
    """Declared primary transport; RTT currently supports channel zero only."""

    transport: Literal["swo", "rtt"]
    rtt_channel: int | None = None

    @classmethod
    def from_value(cls, value: object, *, field: str = "console") -> "ConsoleConfig | None":
        """Validate a manifest declaration; null means unknown."""
        if value is None:
            return None
        if not isinstance(value, dict):
            raise NSXConfigError(f"{field}: expected a mapping or null", field=field)
        if any(key not in {"transport", "rtt_channel"} for key in value):
            raise NSXConfigError(f"{field}: unknown console key", field=field)
        transport = value.get("transport")
        if transport not in ("swo", "rtt"):
            raise NSXConfigError(
                f"{field}.transport: expected 'swo' or 'rtt'", field=f"{field}.transport"
            )
        if transport == "swo":
            if "rtt_channel" in value:
                raise NSXConfigError(
                    f"{field}.rtt_channel: only valid for RTT", field=f"{field}.rtt_channel"
                )
            return cls("swo")
        channel = value.get("rtt_channel", 0)
        if type(channel) is not int or channel != 0:
            raise NSXConfigError(
                f"{field}.rtt_channel: only integer channel 0 is supported",
                field=f"{field}.rtt_channel",
            )
        return cls("rtt", 0)


def validate_console_metadata(data: Mapping[str, object]) -> None:
    """Validate all declarations, including overrides for unselected boards."""
    ConsoleConfig.from_value(data.get("console"))
    targets = data.get("targets")
    supported = targets.get("supported") if isinstance(targets, dict) else None
    if isinstance(supported, dict):
        for board, config in supported.items():
            if isinstance(config, dict) and "console" in config:
                ConsoleConfig.from_value(
                    config["console"], field=f"targets.supported.{board}.console"
                )
