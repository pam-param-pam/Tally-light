"""Application workflows and background operation ownership."""

import threading

from errors import AppError
from cue_sources import AtemSource
from atem_simulator import AtemSimulator
from preferences import PreferenceStore, default_preferences, validate_default_wifi
from relay_profile import load_connection_profile, relay_urls
from scanner import scan
from setup_validation import InvalidSettings, validate_changes
from transmitter import Transmitter
from usb_setup import available_ports, read_settings, write_settings
from serial_monitor import SerialMonitor, SerialMonitorError


class AppBackend:
    def __init__(self, on_event, store=None):
        self.on_event = on_event
        self.store = store or PreferenceStore()
        self.storage_error = ""
        try:
            self.profile = self.store.load()
        except AppError as exc:
            self.storage_error = str(exc)
            self.profile = default_preferences()
        self._tx_stop = None
        self._tx_thread = None
        self._scan_stop = None
        self._scan_thread = None
        self.simulator = AtemSimulator(lambda message: self._emit("sim_status", message))
        self._usb_busy = False
        self._profile_busy = False
        self.connected_tally_port = None
        self._monitor = SerialMonitor(
            on_data=lambda text: self._emit("monitor_data", text),
            on_closed=lambda error: self._emit("monitor_closed", error),
        )

    @property
    def default_wifi_configured(self):
        return bool(self.profile["default_wifi_ssid"] and self.profile["default_wifi_password"])

    def import_profile(self, filename):
        if self._profile_busy:
            raise AppError("A connection profile is already being imported.")
        self._profile_busy = True

        def run():
            error = None
            try:
                self.import_credentials(filename)
            except Exception as exc:
                error = str(exc)
            finally:
                self._profile_busy = False
                self._emit("relay_done", error)

        threading.Thread(target=run, daemon=True).start()

    def disconnect_tally(self):
        self.connected_tally_port = None

    def start_usb(self, operation, port, form=None):
        if self._usb_busy:
            raise AppError("A USB settings operation is already running.")
        if self._monitor.connected:
            raise AppError("Disconnect the serial monitor before using USB settings.")
        if operation not in ("connect", "save"):
            raise AppError("Unknown USB operation.")
        if operation == "save" and port != self.connected_tally_port:
            raise AppError("Connect to the Tally Light before editing its settings.")
        self._usb_busy = True

        def run():
            result = error = None
            try:
                result = self.connect_tally(port) if operation == "connect" else self.save_tally(port, form)
                self.connected_tally_port = port
            except Exception as exc:
                self.connected_tally_port = None
                error = str(exc)
            finally:
                self._usb_busy = False
                self._emit("usb_done", operation, result, error)

        threading.Thread(target=run, daemon=True).start()

    def connect_monitor(self, port):
        if self._usb_busy:
            raise AppError("Wait for the USB settings operation to finish.")
        try:
            self._monitor.connect(port)
        except SerialMonitorError as exc:
            raise AppError(str(exc)) from exc
        self.disconnect_tally()

    def disconnect_monitor(self):
        self._monitor.disconnect()

    def send_monitor_line(self, text):
        try:
            self._monitor.send_line(text)
        except SerialMonitorError as exc:
            raise AppError(str(exc)) from exc

    def close(self):
        self.simulator.stop()
        self.disconnect_monitor()
        self.stop_scan()
        self.stop_transmitter()

    @property
    def relay_enabled(self):
        return self.profile["setup"] == "configured"

    def _emit(self, kind, *values):
        self.on_event(kind, *values)

    def _log(self, message):
        self._emit("log", message)

    def import_credentials(self, filename):
        document = load_connection_profile(filename)
        lights_url = document["relay_url"]
        updated = {**self.profile, "setup": "configured", "relay_url": lights_url,
                   "transmitter_token": document["transmitter_token"],
                   "tally_light_token": document["tally_light_token"]}
        self.store.save(updated)
        self.profile = updated
        self.storage_error = ""
        self._log("Connection profile saved")

    def clear_all(self):
        if self._profile_busy or self._usb_busy:
            raise AppError("Wait for the current settings operation to finish.")
        self.stop_transmitter()
        self.stop_scan()
        self.simulator.stop()
        self.store.clear()
        self.profile = default_preferences()
        self.storage_error = ""
        self._log("Saved application data cleared")

    def save_default_wifi(self, ssid, password):
        if self._profile_busy:
            raise AppError("Wait for the connection profile import to finish.")
        ssid = ssid.strip() if isinstance(ssid, str) else ssid
        validate_default_wifi(ssid, password)
        updated = {**self.profile, "default_wifi_ssid": ssid,
                   "default_wifi_password": password}
        self.store.save(updated)
        self.profile = updated

    def default_wifi(self):
        ssid = self.profile["default_wifi_ssid"]
        password = self.profile["default_wifi_password"]
        if not ssid or not password:
            raise AppError("Set the default Wi-Fi details in Settings first.")
        return ssid, password

    def ports(self):
        return available_ports()

    def connect_tally(self, port):
        return read_settings(port)

    def build_tally_changes(self, form, saved):
        if not self.relay_enabled:
            raise AppError("Import a connection profile before configuring a Tally Light.")
        try:
            source = int(form["source"])
            brightness = int(form["brightness"])
        except (KeyError, ValueError, TypeError) as exc:
            raise AppError("Source and brightness must be numbers.") from exc
        wifi = {"ssid": form["wifi_ssid"].strip()}
        wifi_password = form["wifi_password"]
        if wifi_password and wifi_password != saved["wifi"]["password"]:
            wifi["password"] = wifi_password
        relay = {"url": self.profile["relay_url"]}
        if self.profile["tally_light_token"] != saved["relay"]["token"]:
            relay["token"] = self.profile["tally_light_token"]
        changes = {"name": form["name"].strip(), "source": source,
                   "brightness": brightness, "wifi": wifi, "relay": relay}
        try:
            validate_changes(changes, saved)
        except InvalidSettings as exc:
            raise AppError(str(exc)) from exc
        return changes

    def save_tally(self, port, form):
        snapshot = read_settings(port)
        changes = self.build_tally_changes(form, snapshot["data"]["settings"])
        result = write_settings(port, changes, saved_snapshot=snapshot)
        self._log(f"Settings saved to {snapshot['deviceId']}")
        return result

    def scan_ranges(self):
        return "192.168.1.0/24"

    def start_scan(self, scope):
        if self._scan_thread and self._scan_thread.is_alive():
            raise AppError("A scan is already running.")
        if self.simulator.running:
            scope = f"{scope}, {self.simulator.address}/32"
        stop = threading.Event()
        self._scan_stop = stop

        def worker():
            try:
                scan(scope, stop, lambda found: self._emit("found", found),
                     lambda done, total: self._emit("scan_progress", done, total))
                self._emit("scan_done", "Scan cancelled" if stop.is_set() else "Scan complete")
            except Exception as exc:
                self._emit("scan_done", str(exc))
            finally:
                self._scan_stop = None

        self._scan_thread = threading.Thread(target=worker, daemon=True)
        self._scan_thread.start()

    def stop_scan(self):
        if self._scan_stop:
            self._scan_stop.set()

    def start_transmitter(self, atem_ip):
        if self._profile_busy:
            raise AppError("Wait for the connection profile import to finish.")
        if not self.relay_enabled:
            raise AppError("Import a connection profile in Settings before starting the transmitter.")
        if self._tx_thread and self._tx_thread.is_alive():
            raise AppError("The transmitter is already running.")
        source = AtemSource(atem_ip.strip(), self._transmitter_status)
        _, transmitter_url = relay_urls(self.profile["relay_url"])
        stop = threading.Event()
        worker = Transmitter(
            transmitter_url, self.profile["transmitter_token"], source,
            self._transmitter_status,
            lambda program, preview: self._emit("tx_state", program, preview),
            stop, self._log)
        updated = {**self.profile, "last_atem_ip": atem_ip.strip()}
        self.store.save(updated)
        self.profile = updated
        self._tx_stop = stop

        def run():
            try:
                worker.run()
            except Exception as exc:
                self._emit("tx_status", f"Transmitter stopped: {exc}")
                self._log(f"Transmitter stopped: {exc}")
            finally:
                self._tx_stop = None
                self._tx_thread = None
                self._emit("tx_done")

        self._tx_thread = threading.Thread(target=run, daemon=True)
        self._tx_thread.start()
        self._log("Starting ATEM transmitter")

    def _transmitter_status(self, message):
        self._emit("tx_status", message)
        self._log(message)

    def stop_transmitter(self):
        if self._tx_stop:
            self._tx_stop.set()
            self._log("Stopping transmitter")
