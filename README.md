
# Tally Light

Wireless tally light for use with ATEM switchers. 
It has 2 "modes of operation"

1) Connects to ATEM switcher via local wifi, requires tally to be in the same network as ATEM.

2) Connects to ATEM via "Relay Server" using websockets.
How does it work? Well Tally Light connects to Relay Server websocket which is accessible from the outer internet. Then theres a program in the same network as ATEM that listens for changes and sends data to Relay Server which then sends that data to Tally Light.


The tally Light has it's own setup page, which u can access by clicking the push button, connecting to tally's wifi, and typing `192.168.1.4` in the browser.

For the Tally Light, I used NODEMCU v3 esp8266 esp-12e. I added an external push button, Li-Pol rechargable battery and a charger. The cost was under 15$.






## Relay Server Protocol:
There are 2 endpoints on the Relay Server


| Endpoint  | Description                                                                     |
| :-------- | :------------------------------------------------------------------------------ |
| `/tally`  | For Tally Lights to connect to, and listen for upcoming events                  |
| `/atem`   | For a program that monitors ATEM and sends info about the state of the SWITCHER |


Each event/message consists of a simple json. For example:
```
{"op": int, "t": int, "d": json/string}
```
't' represents an int from 0 to 64. Each Tally Light has it's ATEM source value assigned. When that value equals 't', 
it means that it's designated for the Tally Light. When 't' is 0, it means all Tally Lights have to act on it.
Different OP codes mean different events:


| op  | Event                 | Type                   | Data payload                                                   | Description                                                                                                      |
|:----|:----------------------|:-----------------------|:---------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------|
| `1` | IDENTIFY              | Tally -> Relay         | `{"rId": int}`                                               | must include Room ID, must be sent within 5 seconds of connecting to relay                                       |
| `2` | PING                  | Atem -> Relay -> Tally | `"Hello there"`                                                | program/preview change. pg and pv are program and preview source, each representing an int from 1 to 64          
| `2` | PONG                  | Tally -> Relay -> Atem | `"General Kenobi"`                                             | Atem may send this to tally to check if its still listening                                                      |
| `4` | PROGRAM CHANGE        | Atem -> Relay -> Tally | `{"pg": int, "pv": int}`                                       | Tally must respond to PING event with PONG event to inform that it's still listening                             |
| `5` | NEW TALLY CONNECTED   | Relay -> Atem          | `"New tally connected"`                                        | Sent to atem when a new tally connects                                                                           |
| `6` | CHANGE BRIGHTNESS     | Atem -> Relay -> Tally | `{"b": int}`                                                   | Brightness is an int from 0 to 255, the higher the brighter                                                      |
| `7` | TALLY DISCONNECTED    | Relay -> Atem          | `""`                                                           | Sent to atem when tally disconnects                                                                              |
| `8` | ATEM DISCONNECTED     | Relay -> Tally         | `""`                                                           | Sent to tally when atem disconnects                                                                              |
| `9` | STATUS CHECK          | ATEM -> Relay -> Tally | `""`                                                           | Atem sends this to obtain Tally Lights status info                                                               |
| `9` | STATUS CHECK RESPONSE | Tally -> Relay -> ATEM | `"{"bV": int, "n": string, b": int, "c": int, "s": string}"`   | Sent by tally, bW is battery voltage, b is brightness, c is color, s wifi name, n is tally name |

When connecting to `/atem`, you must include `room-id` header with Room ID 
there can only be 1 client connected to `/atem` per Room ID.

### Parts used
 - [Nodemcu v2](https://botland.com.pl/moduly-wifi-esp8266/4450-modul-wifi-esp-12e-nodemcu-v2-4mb-5903351241328.html)
 - [Li-Pol battery](https://botland.com.pl/akumulatory-li-pol-1s-37v/15613-akumulator-li-pol-akyga-1000mah-1s-37v-zlacze-jst-bec-gniazdo-48x30x7mm-5904422324230.html)
 - [Li-Pol battery charger](https://botland.com.pl/moduly-ladowania-lipol-usb-micro-usb/16979-ladowarka-li-pol-tp4056-pojedyncza-cela-1s-37v-usb-typ-c-z-zabezpieczeniami--5904422326708.html)- [RGB Led](https://botland.com.pl/diody-led-rgb/1667-dioda-led-5mm-rgb-matowa-wsp-katoda-5-szt-5903351244152.html)
 - wires
 - few resistors 10/22/44 ohm for RGB Led
 - few switch buttons
### esp8266 code based on

- [@AronHetLam's Tally Light](https://github.com/AronHetLam/ATEM_tally_light_with_ESP8266)

