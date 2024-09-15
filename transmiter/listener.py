import json
import time

import websocket


def on_message(ws, message):

    print(message)


def on_error(ws, error):
    print(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    print(f"WebSocket closed with status: {close_status_code}, message: {close_msg}")


def on_open(ws):
    # # ws.send("ATEM CONNECTED")
    # ws.send(json.dumps({"op": 1, "t": 1, "d": {"rId": "1234"}}))

    while True:
        ws.send(json.dumps({"op": 4, "t": 1, "d": {"pg": 1, "pv": 2}}))
        time.sleep(1)
        ws.send(json.dumps({"op": 4, "t": 1, "d": {"pg": 2, "pv": 1}}))
        time.sleep(1)




websocket.enableTrace(True)
ws = websocket.WebSocketApp("wss://tally.pamparampam.dev/atem",
                            on_open=on_open,
                            on_message=on_message,
                            on_error=on_error,
                            on_close=on_close,
                            on_reconnect=on_open,
                            header={"room-id": "1234"})

ws.run_forever(reconnect=5)

print(1)