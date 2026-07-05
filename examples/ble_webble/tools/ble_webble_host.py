#!/usr/bin/env python3
"""Simple host-side BLE smoke tool for the NSX ble_webble example."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Sequence

from bleak import BleakClient, BleakScanner

SERVICE_UUID = "19b10000-0000-537e-4f6c-d104768a1214"
HEARTBEAT_UUID = "19b10000-2001-537e-4f6c-d104768a1214"
NOTIFY_UUID = "19b10000-5001-537e-4f6c-d104768a1214"
RGB_UUID = "19b10000-8001-537e-4f6c-d104768a1214"

DEFAULT_NAMES = ("NSX-AP3", "NSX-AP4", "NSX-AP5")


@dataclass(frozen=True)
class DeviceCandidate:
    address: str
    name: str
    rssi: int | None

    def summary(self) -> str:
        rssi = "?" if self.rssi is None else str(self.rssi)
        return f"{self.address} name={self.name} rssi={rssi}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BLE smoke tool for ble_webble")
    parser.add_argument("--list", action="store_true", help="scan and list matching BLE devices, then exit")
    parser.add_argument("--address", help="connect to a specific BLE device address")
    parser.add_argument(
        "--name",
        default="NSX-AP5",
        help="preferred advertised device name when auto-selecting (default: NSX-AP5)",
    )
    parser.add_argument(
        "--scan-seconds",
        type=float,
        default=6.0,
        help="scan duration before auto-selecting a device",
    )
    parser.add_argument(
        "--notify-seconds",
        type=float,
        default=3.0,
        help="time to wait for notify updates after subscribing",
    )
    parser.add_argument(
        "--rgb",
        default="010203",
        help="3-byte RGB value to write as hex (default: 010203)",
    )
    return parser.parse_args()


async def discover_candidates(scan_seconds: float) -> list[DeviceCandidate]:
    devices = await BleakScanner.discover(timeout=scan_seconds, return_adv=True)
    candidates: list[DeviceCandidate] = []
    entries = devices.values() if isinstance(devices, dict) else ((device, None) for device in devices)
    for device, advertisement_data in entries:
        name = device.name or ""
        uuids = {
            uuid.lower() for uuid in ((advertisement_data.service_uuids if advertisement_data else None) or [])
        }
        if name in DEFAULT_NAMES or SERVICE_UUID.lower() in uuids:
            candidates.append(
                DeviceCandidate(
                    address=device.address,
                    name=name or "<unknown>",
                    rssi=(advertisement_data.rssi if advertisement_data else None),
                )
            )
    return candidates


def select_candidate(
    candidates: Sequence[DeviceCandidate], *, preferred_name: str | None, address: str | None
) -> DeviceCandidate:
    if address is not None:
        for candidate in candidates:
            if candidate.address.lower() == address.lower():
                return candidate
        raise SystemExit(f"Requested address {address} not found in BLE scan results")

    if preferred_name is not None:
        for candidate in candidates:
            if candidate.name == preferred_name:
                return candidate

    if len(candidates) == 1:
        return candidates[0]

    details = "\n".join(f"  - {candidate.summary()}" for candidate in candidates)
    raise SystemExit(
        "Multiple BLE devices matched. Re-run with --address to disambiguate:\n" + details
    )


async def run_demo(args: argparse.Namespace) -> int:
    if args.address is None or args.list:
        candidates = await discover_candidates(args.scan_seconds)
    else:
        candidates = []

    if args.list:
        if not candidates:
            raise SystemExit("No matching BLE devices found")
        for candidate in candidates:
            print(candidate.summary())
        return 0

    if args.address is not None:
        target = DeviceCandidate(address=args.address, name=args.name or "<explicit>", rssi=None)
    else:
        if not candidates:
            raise SystemExit("No matching BLE devices found")
        target = select_candidate(candidates, preferred_name=args.name, address=args.address)
    print(f"device: {target.summary()}")

    rgb = bytes.fromhex(args.rgb)
    if len(rgb) != 3:
        raise SystemExit("--rgb must decode to exactly 3 bytes")

    notify_values: list[bytes] = []

    def handle_notify(_: str, data: bytearray) -> None:
        notify_values.append(bytes(data))
        print(f"notify: {bytes(data).hex()}")

    async with BleakClient(target.address) as client:
        print(f"connected: {client.is_connected}")
        services = client.services
        service = services.get_service(SERVICE_UUID)
        if service is None:
            raise SystemExit(f"Service {SERVICE_UUID} not found")

        heartbeat = await client.read_gatt_char(HEARTBEAT_UUID)
        print(f"heartbeat: {heartbeat.hex()}")

        await client.start_notify(NOTIFY_UUID, handle_notify)
        await asyncio.sleep(args.notify_seconds)
        await client.stop_notify(NOTIFY_UUID)

        await client.write_gatt_char(RGB_UUID, rgb, response=True)
        rgb_readback = await client.read_gatt_char(RGB_UUID)
        print(f"rgb-readback: {rgb_readback.hex()}")

        if notify_values:
            print(f"notify-count: {len(notify_values)}")
        else:
            print("notify-count: 0")
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(run_demo(args))


if __name__ == "__main__":
    raise SystemExit(main())
