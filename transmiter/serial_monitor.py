import codecs
import threading


class SerialMonitorError(Exception):
    pass


class SerialMonitor:
    def __init__(self, on_data, on_closed):
        self.on_data = on_data
        self.on_closed = on_closed
        self._connection = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @property
    def connected(self):
        with self._lock:
            return self._connection is not None and self._connection.is_open

    def connect(self, port_name):
        if not port_name:
            raise SerialMonitorError("Choose a USB serial port.")
        if self.connected:
            raise SerialMonitorError("The serial monitor is already connected.")

        connection = None
        try:
            import serial

            connection = serial.Serial()
            connection.port = port_name
            connection.baudrate = 115200
            connection.bytesize = serial.EIGHTBITS
            connection.parity = serial.PARITY_NONE
            connection.stopbits = serial.STOPBITS_ONE
            connection.timeout = 0.1
            connection.write_timeout = 2
            connection.xonxoff = False
            connection.rtscts = False
            connection.dsrdtr = False
            connection.dtr = False
            connection.rts = False
            connection.open()
        except (OSError, ValueError) as exc:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            raise SerialMonitorError(f"Could not open {port_name}: {exc}") from exc

        self._stop.clear()
        with self._lock:
            self._connection = connection
        self._thread = threading.Thread(target=self._read, args=(connection,), daemon=True)
        self._thread.start()

    def disconnect(self):
        self._stop.set()
        with self._lock:
            connection = self._connection
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass

    def send_line(self, text):
        with self._lock:
            connection = self._connection
        if connection is None or not connection.is_open:
            raise SerialMonitorError("Connect the serial monitor first.")
        try:
            connection.write((text + "\n").encode("utf-8"))
            connection.flush()
        except (OSError, ValueError) as exc:
            raise SerialMonitorError(f"Could not write to the serial port: {exc}") from exc

    def _read(self, connection):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        error = None
        try:
            while not self._stop.is_set() and connection.is_open:
                chunk = connection.read(connection.in_waiting or 1)
                if chunk:
                    text = decoder.decode(chunk)
                    if text:
                        self.on_data(text)
        except (OSError, ValueError) as exc:
            if not self._stop.is_set():
                error = str(exc)
        finally:
            remaining = decoder.decode(b"", final=True)
            if remaining:
                self.on_data(remaining)
            try:
                connection.close()
            except OSError:
                pass
            with self._lock:
                if self._connection is connection:
                    self._connection = None
                    self._thread = None
            self.on_closed(error)
