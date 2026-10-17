"""Find ATEM switchers on local or user-entered IPv4 subnets."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import ipaddress
import socket
import threading

import psutil
import PyATEMMax


MAX_TARGETS = 2048


@dataclass(frozen=True)
class FoundSwitcher:
    ip: str
    model: str
    program: int | None = None
    preview: int | None = None
    program_name: str = ""
    preview_name: str = ""
    ready: bool = False


def local_ranges():
    """Return one practical scan range per local IPv4 adapter."""
    ranges = set()
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if address.family != socket.AF_INET or not address.netmask:
                continue
            try:
                interface = ipaddress.IPv4Interface(f"{address.address}/{address.netmask}")
            except ValueError:
                continue
            if interface.ip.is_loopback or interface.ip.is_link_local:
                continue
            network = interface.network
            # A /16 or wider is too large for one quick discovery pass. Start
            # near this adapter; the scope field accepts any other CIDR.
            if network.num_addresses > MAX_TARGETS:
                network = ipaddress.IPv4Network(f"{interface.ip}/24", strict=False)
            ranges.add(network)
    return sorted(ranges, key=lambda item: (int(item.network_address), item.prefixlen))


def targets_for_scope(scope):
    """Parse comma/whitespace-separated CIDRs, deduplicate, and bound work."""
    text = scope.replace(",", " ").strip()
    if not text:
        raise ValueError("Enter at least one IPv4 subnet, such as 192.168.1.0/24.")
    targets = set()
    for part in text.split():
        try:
            network = ipaddress.IPv4Network(part, strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid IPv4 subnet: {part}") from exc
        if network.num_addresses > MAX_TARGETS + 2:
            raise ValueError(f"{network} is too large. Enter one or more smaller CIDRs (up to {MAX_TARGETS} hosts total).")
        targets.update(network.hosts())
        if len(targets) > MAX_TARGETS:
            raise ValueError(f"Scan limit is {MAX_TARGETS} hosts. Narrow the CIDRs and try again.")
    return [str(address) for address in sorted(targets)]


def source_value(value):
    number = getattr(value, "value", value)
    return number if type(number) is int and 1 <= number <= 65535 else None


def source_name(switcher, source):
    if source is None:
        return ""
    try:
        value = switcher.inputProperties[source].shortName
        return str(getattr(value, "value", value) or "")
    except (AttributeError, KeyError, IndexError, TypeError):
        return ""


def probe_ip(ip, stop=None, *, atem_factory=None):
    """Short UDP check, then full ATEM handshake for responsive hosts."""
    if stop is not None and stop.is_set():
        return None
    switcher = (atem_factory or PyATEMMax.ATEMMax)()
    try:
        switcher.connect(ip, connTimeout=2)
        if not switcher.waitForConnection(infinite=False, timeout=0.6, waitForFullHandshake=False):
            return None
        if stop is not None and stop.is_set():
            return None
        ready = switcher.waitForConnection(infinite=False, timeout=3)
        if not ready:
            return FoundSwitcher(ip, "ATEM responded", ready=False)
        program = source_value(switcher.programInput[0].videoSource)
        preview = source_value(switcher.previewInput[0].videoSource)
        return FoundSwitcher(ip, str(switcher.atemModel or "ATEM"), program, preview,
                             source_name(switcher, program), source_name(switcher, preview), True)
    finally:
        switcher.disconnect()


def scan(scope, stop: threading.Event, on_found, on_progress):
    targets = targets_for_scope(scope)
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(probe_ip, ip, stop): ip for ip in targets}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            if stop.is_set():
                for pending in futures:
                    pending.cancel()
                break
            try:
                found = future.result()
            except Exception:
                found = None  # A failed address does not abort discovery.
            if found:
                on_found(found)
            if completed == len(targets) or completed % 10 == 0:
                on_progress(completed, len(targets))
