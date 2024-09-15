
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
{"op": 4, "t": -1, "d": ""}
```
't' represents an int from -1 to 64. Each Tally Light has it's ATEM source value assigned. When 't' is equal to it, it means that the designated for the Tally Light. When 't' is 0, it means all Tally Lights have to act on it.
Diffrent OP codes mean diffrent events:

| op  | Type                 | Data payload        |  Description                                  |
| :---| :------------------- | :-------------------| :-------------------------------------------- |
| `1` | From ATEM to Tally | `{"pg": pg, "pv": pv}`| program/preview change. pg and pv are program and preview source, each representing an int from 1 to 64
| `2` | From ATEM to Tally | `"Hello there"`       | PING, sent from ATEM to make sure Tally is still listening |
| `3` | From Tally to ATEM | `"General Kenobi"`    | PONG, sent from Tally to inform ATEM that it's still listening |
| `4` | From ATEM to Tally | `{"b": brightness}`  |Brightness is an int from 0 to 255, the higher the brighter|




### Based on

- [@AronHetLam's Tally Light](https://github.com/AronHetLam/ATEM_tally_light_with_ESP8266)

