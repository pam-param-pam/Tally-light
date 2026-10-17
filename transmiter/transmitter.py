"""Send cues from a source to the relay and maintain its WebSocket session."""

import json
import time
from uuid import uuid4

import websocket


class ConnectionRejected(Exception):
    pass


class Transmitter:
    def __init__(self, relay_url, token, source, status, state, stop, log):
        self.relay_url = relay_url
        self.token = token
        self.source = source
        self.status = status
        self.state = state
        self.stop = stop
        self.log = log

    def run(self):
        try:
            while not self.stop.is_set():
                try:
                    self._session()
                except ConnectionRejected as exc:
                    self.status(str(exc))
                    return
                except Exception as exc:
                    self.status(f"Connection lost: {exc}. Retrying…")
                self.stop.wait(3)
            self.status("Transmitter stopped")
        finally:
            self.source.close()

    @staticmethod
    def _send(socket, message_type, data, **fields):
        frame = {"type": message_type, "id": uuid4().hex, "data": data, **fields}
        socket.send(json.dumps(frame, separators=(",", ":")))

    def _session(self):
        self.status("Connecting to relay…")
        socket = websocket.create_connection(self.relay_url, timeout=5)
        try:
            self._send(socket, "hello", {"token": self.token})
            reply = json.loads(socket.recv())
            if reply["type"] == "error":
                raise ConnectionRejected(reply["data"]["message"])
            if reply["type"] != "welcome":
                raise RuntimeError("Unexpected relay handshake")
            socket.settimeout(0.01)
            self.status("Relay connected")
            sequence = 0
            while not self.stop.is_set():
                cue = self.source.read(time.monotonic())
                if cue is not None:
                    program, preview = cue
                    sequence += 1
                    self._send(socket, "atem.state", {
                        "program": program, "preview": preview, "sequence": sequence,
                    })
                    self.state(program, preview)
                    self.log(f"Sent cue {sequence}: program {program or '—'}, preview {preview or '—'}")
                self._receive(socket)
        finally:
            socket.close()
            self.source.close()

    def _receive(self, socket):
        try:
            message = socket.recv()
        except websocket.WebSocketTimeoutException:
            return
        if message == "":
            raise RuntimeError("Relay closed the connection")
        frame = json.loads(message)
        if frame["type"] == "ping":
            self._send(socket, "pong", {}, replyTo=frame["id"])
        elif frame["type"] == "error":
            raise RuntimeError(frame["data"]["message"])
