"""Shared J-Link selection policy; intent resolution never accesses USB."""

from dataclasses import dataclass

from . import tooling
from ._errors import NSXConfigError


@dataclass(frozen=True, slots=True)
class ProbeRequest:
    identity: str | None
    discover: bool

    def __post_init__(self) -> None:
        if type(self.discover) is not bool:
            raise NSXConfigError("discover_probe must be a boolean.")
        if self.identity is not None and self.discover:
            raise NSXConfigError("Use either --probe-serial or --discover-probe, not both.")


def validate_probe_request(serial: str | None, discover: bool = False) -> None:
    """Validate a J-Link request before updating a build or enumerating USB."""
    ProbeRequest(serial, discover)
    if serial is not None and (
        not isinstance(serial, str)
        or not serial.isascii()
        or not serial.isdecimal()
        or int(serial) <= 0
    ):
        raise NSXConfigError("Probe serial must be a positive decimal USB serial number.")


@dataclass(frozen=True, slots=True)
class ProbeSelection:
    """A validated exact serial, or deferred USB discovery."""

    serial: str | None

    @classmethod
    def from_request(
        cls, serial: str | None, discover: bool = False, configured: str | None = None
    ) -> "ProbeSelection":
        validate_probe_request(serial, discover)
        validate_probe_request(configured)
        return cls(serial if serial is not None else None if discover else configured)

    def resolve(self) -> str:
        """Resolve once inside the operation's execution/worker boundary."""
        if self.serial is not None:
            return self.serial
        probes = [p.probe for p in tooling._list_jlink_inventory() if p.transport == "USB"]
        if len(probes) != 1:
            raise NSXConfigError(
                f"Found {len(probes)} eligible local USB J-Link probes; "
                "use `nsx probes` and pass --probe-serial."
            )
        serial = probes[0].serial
        validate_probe_request(serial)
        return serial
