/*
    Copyright (C) 2023 Aron N. Het Lam, aronhetlam@gmail.com

    This program makes an ESP8266 into a wireless tally light system for ATEM switchers,
    by using Kasper Skårhøj's (<https://skaarhoj.com>) ATEM client libraries for Arduino.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
*/

#include "Arduino.h"
//Perform initial setup on power on
//Handle the change of states in the program
void changeState(uint8_t stateToChangeTo);

//Websocket event, on connect, on disconnect, on text, on binary etc
//void webSocketEvent(WStype_t type, uint8_t * payload, size_t length);

//Loop that checks for button press
void buttonLoop();

//Set the color of both LEDs
void setLedColor(uint8_t color);

//Set the color of a LED using the given pins
void setLED(uint8_t color, int pinRed, int pinGreen, int pinBlue);

void analogWriteWrapper(uint8_t pin, uint8_t value);

int getTallyState(uint16_t tallyNo);

int getLedColor(int tallyNo);

//Serve setup web page to client, by sending HTML with the correct variables
void handleRoot();

//Save new settings from client in EEPROM and restart the ESP8266 module
void handleSave();

//Send 404 to client in case of invalid webpage being requested.
void handleNotFound();

String getSSID();

void setWiFi(String ssid, String pwd);

// void improvCallback(improv::ImprovCommand d);
//Commented out for users without batteries - Also timer is not done properly
//Main loop for things that should work every second
void batteryLoop();
