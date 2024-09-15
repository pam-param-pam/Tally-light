
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
't' represents an int from 0 to 64. Each Tally Light has it's ATEM source value assigned. When 't' is equal to it, 
it means that the designated for the Tally Light. When 't' is 0, it means all Tally Lights have to act on it.
Different OP codes mean different events:


| op  | Event               | Type                          | Data payload              | Description                                                                                             |
|:----|:--------------------|:------------------------------|:--------------------------|:--------------------------------------------------------------------------------------------------------|
| `1` | IDENTIFY            | Tally -> Relay                | `{"rId": int}`            | must include Room ID, must be sent within 5 seconds of connecting to relay                              |
| `2` | PING                | Atem -> Relay -> Tally        | `{"pg": int, "pv": int}`  | program/preview change. pg and pv are program and preview source, each representing an int from 1 to 64 
| `3` | PONG                | Tally -> Relay -> Atem        | `"Hello there"`           | Atem may send this to tally to check if its still listening                                             |
| `4` | PROGRAM CHANGE      | Atem -> Relay -> Tally        | `"General Kenobi"`        | Tally must respond to PING event with PONG event to inform that it's still listening                    |
| `5` | NEW TALLY CONNECTED | Relay -> Atem                 | `"New tally connected"}`  | Sent to atem when a new tally connects                                                                  |
| `6` | CHANGE BRIGHTNESS   | Atem -> Relay -> Tally        | `{"b": int}`              | Brightness is an int from 0 to 255, the higher the brighter                                             |
| `7` | TALLY DISCONNECTED  | Relay -> Atem        | `":("`                    | Sent to atem when tally disconnects                                                                     |
| `8` | ATEM DISCONNECTED   | Relay -> Tally        | `":("`                    | Sent to tally when atem disconnects                                                                     |


when connecting to `/atem`, you must include `room-id` header with Room ID 

### Based on

- [@AronHetLam's Tally Light](https://github.com/AronHetLam/ATEM_tally_light_with_ESP8266)

