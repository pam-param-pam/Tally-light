import re
import sys
import time
import threading
import PyATEMMax
import websocket
import json

from colorama import init
from websocket import WebSocketConnectionClosedException
init()
from colorama import Fore, Back, Style

"""
op_codes:
1 - authentication/identify, sent from tally/atem -> relay
2 - PING, sent from atem -> relay -> tally
3 - PONG, sent from tally -> relay -> atem
4 - program change, sent from atem -> relay -> tally
5 - new tally connected, sent from relay -> atem
6 - change brightness, sent from atem -> relay -> tally
"""

while True:
    websocket_address = input(f"{Fore.MAGENTA}Please enter relay websocket address: {Fore.LIGHTGREEN_EX}")
    if websocket_address == "skip":
        websocket_address = "wss://tally.pamparampam.dev/atem"
        break
    ws_addr_pattern = r"^wss?:\/\/[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(\/[a-zA-Z0-9\/._-]*)?$"
    if not re.match(ws_addr_pattern, websocket_address):
        print(f"{Fore.RED}WEBSOCKET ADDRESS ISN'T VALID")
        print(f"{Fore.YELLOW}Websocket address should look like:")
        print(f"{Fore.LIGHTBLUE_EX}protocol://domain/path")
        print(f"{Fore.YELLOW}for example")
        print(f"{Fore.LIGHTBLUE_EX}wss://tally.pamparampam.dev/atem")
    else:
        break

while True:
    atem_ip = input(f"{Fore.MAGENTA}Please enter ATEM IP address: {Fore.LIGHTGREEN_EX}")
    if atem_ip == "skip":
        atem_ip = "192.168.1.16"
        break
    atem_ip_pattern = r"^((\d{1,3}\.){3}\d{1,3}|\[[a-fA-F0-9:]+\])(:\d{1,5})?$"
    if not re.match(atem_ip_pattern, atem_ip):
        print(f"{Fore.RED}Atem IP ISN'T VALID")
        print(f"{Fore.YELLOW}Atem IP should look like:")
        print(f"{Fore.LIGHTBLUE_EX}192.168.1.16")
    else:
        break

while True:
    room_id = input(f"{Fore.MAGENTA}Please enter room_id: {Fore.LIGHTGREEN_EX}")
    if 4 > len(room_id) > 16:
        print(f"{Fore.RED}Room ID must be between 4 and 16 characters")
    else:
        break

# Initialize ATEM switcher connection
switcher = PyATEMMax.ATEMMax()
switcher.connect(atem_ip)

print(f"{Fore.CYAN}PROGRAM START WITH:\nWebsocket Address: "
      f"{websocket_address}\n"
      f"Relay room ID: {room_id}\n"
      f"Atem IP: {atem_ip}")

print(f"{Fore.LIGHTBLUE_EX}===Connecting to ATEM SWITCHER(timeout=3)===")

switcher.waitForConnection(timeout=3)
if not switcher.connected:
    print(f"{Fore.RED}ERROR:  CAN'T CONNECT TO ATEM SWITCHER!!!")
    print(f"{Fore.LIGHTRED_EX}Restart program with a correct ATEM IP, make sure the ATEM is in the same network as this computer.")
    sys.exit(0)
else:
    print(f"{Fore.GREEN}Connected to Atem Switcher!")

last_program = switcher.programInput[0].videoSource.value
last_preview = switcher.previewInput[0].videoSource.value


# Function to handle ATEM switcher tally updates
def handle_tally_updates():
    global last_program
    global last_preview

    while True:
        program = switcher.programInput[0].videoSource.value
        preview = switcher.previewInput[0].videoSource.value
        if preview != last_preview or program != last_program:
            send_websocket_message(json.dumps({"op": 4, "t": 0, "d": {"pg": program, "pv": preview}}))
            last_program = program
            last_preview = preview

        time.sleep(0.01)  # Avoid hogging processor..


# Initialize WebSocket connection
def on_message(ws, message):
    json_message = json.loads(message)

    op_code = json_message['op']
    tally_number = json_message['t']
    if op_code == 5:  # New tally connected OP CODE
        print(f"{Fore.LIGHTBLUE_EX}Tally connected: tally_number: {tally_number}")
        send_websocket_message(json.dumps({"op": 4, "t": 0, "d": {"pg": last_program, "pv": last_preview}}))
    elif op_code == 3:
        print(f"{Fore.LIGHTRED_EX}Tally number {tally_number} has disconnected from the relay server, reason unknown!")
    elif op_code == 7:  # Tally disconnected
        print(f"{Fore.LIGHTRED_EX}Tally disconnected: tally_number: {tally_number}")

def on_error(ws, error):
    if "Handshake status 403 Access denied" in str(error):
        print(f"{Fore.RED}Websocket Handshake failed, 403 Access denied.")
        print(f"{Fore.LIGHTRED_EX}There is ATEM listener instance already running or room ID is invalid.")


def on_close(ws, close_status_code, close_msg):
    print(f"{Fore.RED}WebSocket closed with status: {close_status_code}, message: {close_msg}")


def on_open(ws):
    send_websocket_message(json.dumps({"op": 4, "t": 0, "d": {"pg": last_program, "pv": last_preview}}))
    # Start threads
    tally_thread = threading.Thread(target=handle_tally_updates)
    tally_thread.start()


def send_websocket_message(message):
    try:
        ws.send(message)
    except WebSocketConnectionClosedException:
        print(f"{Fore.RED}ERROR Couldn't send message, websocket is CLOSED")

#websocket.enableTrace(True)
ws = websocket.WebSocketApp(websocket_address,
                            on_open=on_open,
                            on_message=on_message,
                            on_error=on_error,
                            on_close=on_close,
                            on_reconnect=on_open,
                            header={"room-id": room_id})


# Thread for WebSocket handling
def run_websocket():
    print(f"{Fore.LIGHTBLUE_EX}===CONNECTING TO WEBSOCKET===")
    ws.run_forever(reconnect=5)


websocket_thread = threading.Thread(target=run_websocket)
websocket_thread.start()


# Thread for command line commands
try:
    while True:
        try:
            command = input(f"{Fore.MAGENTA}Enter command:\n{Fore.LIGHTGREEN_EX}")
            if command == "help":
                print(f"{Fore.YELLOW}USAGE: <command> <tally_code> <arg>")
                print(f"Commands:")
                print(f"{Fore.LIGHTBLUE_EX}ping <tally_code>       tests connection to tally, should immediately return PONG")
                print(f"{Fore.LIGHTBLUE_EX}brightness <tally_code> <value from 0 - 255>      changes brightness of tally lights")

                continue
            split_values = command.split(" ")

            command = split_values[0]
            t_code = split_values[1]

            args = []
            if len(split_values) >= 3:
                args = split_values[2:]

            if command == "ping":
                send_websocket_message(json.dumps({"op": 2, "t": int(t_code), "d": "Hello there"}))
            elif command == "brightness":
                send_websocket_message(json.dumps({"op": 6, "t": int(t_code), "d": ''.join(args)}))
            else:
                print(f"{Fore.RED}Command not found try: help")
        except (ValueError, IndexError):
            print(f"{Fore.RED}ValueError, most likely incorrect args or unknown command, try: help")
        time.sleep(1)

except (KeyboardInterrupt, EOFError):
    print(f"{Fore.LIGHTRED_EX}\nCtrl+C detected, jokes on you, its not implemented. Just close the terminal...")

    sys.exit(0)
