"""ATEM cue reading, independent of relay transport and GUI."""

import ipaddress
import time

import PyATEMMax

from errors import AppError
from scanner import source_value


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
                    self.status(f"Relay connected Â· ATEM {self.address} connected")
            except (OSError, RuntimeError):
                pass
            finally:
                if self._switcher is None:
                    candidate.disconnect()
                    self._next_attempt = time.monotonic() + 3
                    self.status(f"Relay connected Â· waiting for ATEM {self.address}")
        current = (None, None)
        if self._switcher is not None:
            if self._switcher.connected:
                current = (source_value(self._switcher.programInput[0].videoSource),
                           source_value(self._switcher.previewInput[0].videoSource))
            else:
                self.close()
                self._next_attempt = now + 3
                self.status("ATEM disconnected Â· reconnecting")
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
