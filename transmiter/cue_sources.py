"""ATEM and mock cue generation, independent of relay transport and GUI."""

import ipaddress
import random
import threading
import time
from dataclasses import dataclass

import PyATEMMax

from errors import AppError
from scanner import source_value


@dataclass(frozen=True)
class MockSettings:
    first: int
    last: int
    interval_ms: int

    def __post_init__(self):
        if not 1 <= self.first < self.last <= 255:
            raise AppError("Mock source range must contain at least two sources between 1 and 255.")
        if not 10 <= self.interval_ms <= 60000:
            raise AppError("Mock cue interval must be between 10 and 60,000 milliseconds.")

    @classmethod
    def from_values(cls, first, last, interval_ms):
        try:
            values = int(first), int(last), int(interval_ms)
        except (ValueError, TypeError) as exc:
            raise AppError("Enter whole numbers for mock source limits and cue interval.") from exc
        return cls(*values)


class MockSource:
    def __init__(self, settings, status):
        self.settings = settings
        self.status = status
        self.pause = threading.Event()
        self._was_paused = False
        self._next_cue = 0

    def read(self, now):
        paused = self.pause.is_set()
        if paused != self._was_paused:
            self.status("Mock transmitter paused" if paused else "Mock transmitter resumed")
            self._was_paused = paused
            self._next_cue = 0
        if paused or now < self._next_cue:
            return None
        self._next_cue = now + self.settings.interval_ms / 1000
        return tuple(random.sample(range(self.settings.first, self.settings.last + 1), 2))

    def close(self):
        self._next_cue = 0


class AtemSource:
    def __init__(self, address, status):
        try:
            ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError as exc:
            raise AppError("Enter a valid ATEM IPv4 address.") from exc
        self.address = address
        self.status = status
        self._switcher = None
        self._next_attempt = 0
        self._last_state = None
        self._last_sent = 0

    def read(self, now):
        if self._switcher is None and now >= self._next_attempt:
            candidate = PyATEMMax.ATEMMax()
            try:
                candidate.connect(self.address, connTimeout=3)
                if candidate.waitForConnection(infinite=False, timeout=4):
                    self._switcher = candidate
                    self.status(f"Relay connected · ATEM {self.address} connected")
            except (OSError, RuntimeError):
                pass
            finally:
                if self._switcher is None:
                    candidate.disconnect()
                    self._next_attempt = time.monotonic() + 3
                    self.status(f"Relay connected · waiting for ATEM {self.address}")
        current = (None, None)
        if self._switcher is not None:
            if self._switcher.connected:
                current = (source_value(self._switcher.programInput[0].videoSource),
                           source_value(self._switcher.previewInput[0].videoSource))
            else:
                self.close()
                self._next_attempt = now + 3
                self.status("ATEM disconnected · reconnecting")
        if current != self._last_state or now - self._last_sent >= 5:
            self._last_state = current
            self._last_sent = now
            return current
        return None

    def close(self):
        if self._switcher is not None:
            self._switcher.disconnect()
            self._switcher = None
        self._last_state = None
