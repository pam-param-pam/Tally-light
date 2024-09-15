#include "ATEM_tally_light.hpp"

//Include libraries:
#include <Arduino.h>
#include <ArduinoJson.h>
#include <EEPROM.h>

#include <ESP8266WebServer.h>
#include <ESP8266WiFi.h>
#include <WebSocketsClient.h>

#include <Hash.h>
#include <ATEMmin.h>



#define DISPLAY_NAME "Tally Light"

//Define LED1 color pins
#ifndef PIN_RED1
#define PIN_RED1    0 // D3
#endif
#ifndef PIN_GREEN1
#define PIN_GREEN1  5  // D1
#endif
#ifndef PIN_BLUE1
#define PIN_BLUE1   13  // D7
#endif
#define LED_BUILTIN2 16

int BUTTON_PIN = 4;  //D6    


//Define LED colors
#define LED_OFF     0
#define LED_RED     1
#define LED_GREEN   2
#define LED_BLUE    3
#define LED_YELLOW  4
#define LED_PINK    5
#define LED_WHITE   6
#define LED_ORANGE  7


//Define states
#define STATE_STARTING                  0
#define STATE_CONNECTING_TO_WIFI        1
#define STATE_CONNECTING_TO_SWITCHER    2
#define STATE_CONNECTING_TO_RELAY       3
#define STATE_SWITCHER_RUNNING          4
#define STATE_RELAY_RUNNING             5
#define SOFT_AP_ON                      6


//Define modes of operation
#define MODE_NORMAL                     1
#define MODE_PREVIEW_STAY_ON            2
#define MODE_PROGRAM_ONLY               3
#define MODE_ON_AIR                     4

#define TALLY_FLAG_OFF                  0
#define TALLY_FLAG_PROGRAM              1
#define TALLY_FLAG_PREVIEW              2


ESP8266WebServer server(80);

WebSocketsClient webSocket;

ATEMmin atemSwitcher;

uint8_t state = STATE_STARTING;

//Define struct for holding tally settings (mostly to simplify EEPROM read and write, in order to persist settings)
struct Settings {
    bool useRelayServer;
    char relayWsHost[64] = "";
    char relayWsPath[32] = "";
    uint16_t relayWsPort;
    char tallyName[32] = "";
    uint8_t tallyNumber;
    bool staticIP;
    IPAddress tallyIP;
    IPAddress tallySubnetMask;
    IPAddress tallyGateway;
    IPAddress switcherIP;
    uint8_t ledBrightness;
};

Settings settings;

bool firstRun = true;


//Vars for battery loop that monitors battery voltage
unsigned long batteryElapsedTime = 0;
unsigned long baterryStartTime = 0;  
bool betteryLedState = false;
double uBatt = 0;
char buffer[3];

//Vars for button loop that monitors for push button change to enable/disable WIFI station mode for tally setup site
int buttonState = LOW;      
int buttonReading;           
int buttonPrevious = buttonState;   




void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_DISCONNECTED:
            Serial.printf("[WSc] Disconnected!\n");
            break;
        case WStype_CONNECTED: 
            Serial.printf("[WSc] Connected to url: %s\n",  payload);
            // webSocket.sendTXT("Connected");
            break;
        case WStype_TEXT: {
            Serial.printf("[WSc] got text: %s\n", payload);

            StaticJsonDocument<200> doc;
            DeserializationError error = deserializeJson(doc, payload, length);
            if (error) { 
              Serial.println("Coulnd't parse json:");
              return;
            }
            uint8_t t_code = doc["t"];
            uint8_t op_code = doc["op"];

            if (t_code != settings.tallyNumber + 1 && t_code != 0) {
              Serial.println("Command not send to us!");
              return;
            }
            if (op_code == 1) { // program/preview change
              setLedColor(LED_OFF);

              uint8_t preview = doc["d"]["pv"];
              if (preview == settings.tallyNumber + 1) { 
                setLedColor(LED_GREEN);
                Serial.println("Set green");

              }

              uint8_t program = doc["d"]["pg"];
              if (program == settings.tallyNumber + 1) {
                setLedColor(LED_RED);
                Serial.println("Set red");

              }

            } 
            else if (op_code == 2) { //test connection, we need to respond!
              JsonDocument doc;
              doc["op"] = 3; // test connection opcode(from tally)
              doc["t"] = settings.tallyNumber + 1;
              doc["d"] = "General Kenobi";
              String jsonString;
              serializeJson(doc, jsonString);
              webSocket.sendTXT(jsonString);
            } else if (op_code == 5) { //change brightness
              int brightness = doc["d"];
              settings.ledBrightness = brightness;

            }
            
            
            
            break;
        }
        case WStype_BIN:
            Serial.printf("[WSc] got binary length: %u\n", length);
            hexdump(payload, length);
            break;
    }

}
//Perform initial setup on power on
void setup() {
    
    //Start Serial
    Serial.begin(115200);
    Serial.println("########################");
    Serial.println("Serial started");

    //Init builtin led pins 
    pinMode(LED_BUILTIN, OUTPUT); 
    pinMode(LED_BUILTIN2, OUTPUT); 

    // Initialize the button.
    pinMode(BUTTON_PIN, INPUT_PULLUP);

    //Init pins for LED
    pinMode(PIN_RED1, OUTPUT);
    pinMode(PIN_GREEN1, OUTPUT);
    pinMode(PIN_BLUE1, OUTPUT);

    //turn off two builtin leds
    digitalWrite(LED_BUILTIN, HIGH);
    digitalWrite(LED_BUILTIN2, HIGH);

   
    //Setup current-measuring pin
    pinMode(A0, INPUT);

    // //Read settings from EEPROM. WIFI settings are stored separately by the ESP
    EEPROM.begin(sizeof(settings)); //Needed on ESP8266 module, as EEPROM lib works a bit differently than on a regular Arduino
    EEPROM.get(0, settings);

    Serial.println(settings.tallyName);

    if (settings.staticIP && settings.tallyIP != IPADDR_NONE) {
        WiFi.config(settings.tallyIP, settings.tallyGateway, settings.tallySubnetMask);
    } else {
        settings.staticIP = false;
    }


    //Put WiFi into station mode and make it connect to saved network
    WiFi.mode(WIFI_STA); 
    WiFi.hostname((String)settings.tallyName + " setup");
    WiFi.setAutoReconnect(true);
    WiFi.begin();

    Serial.println("------------------------");
    Serial.println("Connecting to WiFi...");
    Serial.println("Network name (SSID): " + getSSID());

    // Initialize and begin HTTP server for handeling the web interface
    server.on("/", handleRoot);
    server.on("/save", handleSave);
    server.onNotFound(handleNotFound);
    server.begin();

    //Set state to connecting before entering loop
    changeState(STATE_CONNECTING_TO_WIFI);

}

void loop() {
    switch (state) {
        case STATE_CONNECTING_TO_WIFI:
            if (WiFi.status() == WL_CONNECTED) {
                WiFi.mode(WIFI_STA); // Disable softAP if connection is successful
                Serial.println("------------------------");
                Serial.println("Connected to WiFi:   " + getSSID());
                Serial.println("IP:                  " + WiFi.localIP().toString());
                Serial.println("Subnet Mask:         " + WiFi.subnetMask().toString());
                Serial.println("Gateway IP:          " + WiFi.gatewayIP().toString());

                if (settings.useRelayServer) {
                  changeState(STATE_CONNECTING_TO_RELAY);
                } else {
                  changeState(STATE_CONNECTING_TO_SWITCHER);
                }
            } else if (firstRun) {
                firstRun = false;
                Serial.println("Unable to connect to WiFi");
            }
            break;

        case STATE_CONNECTING_TO_SWITCHER:
            // Initialize a connection to the switcher:
            if (firstRun && !atemSwitcher.isConnected()) {
                atemSwitcher.begin(settings.switcherIP);
                atemSwitcher.serialOutput(0xff); //Makes Atem library print debug info
                Serial.println("------------------------");
                Serial.println("Connecting to switcher...");
                Serial.println((String)"Switcher IP:         " + settings.switcherIP[0] + "." + settings.switcherIP[1] + "." + settings.switcherIP[2] + "." + settings.switcherIP[3]);
                firstRun = false;
            }
            atemSwitcher.runLoop();
            if (atemSwitcher.isConnected()) {
                changeState(STATE_SWITCHER_RUNNING);
                Serial.println("Connected to switcher");
            }
            break;
      
        case STATE_CONNECTING_TO_RELAY: {
          if (firstRun) {
            if (!webSocket.isConnected())
                Serial.println("Connecting to relay server...");
                Serial.println((String)"Switcher Host:         " + settings.relayWsHost);
                Serial.println((String)"Switcher Port:         " + settings.relayWsPort);
                Serial.println((String)"Switcher path:         " + settings.relayWsPath);

                webSocket.beginSSL(settings.relayWsHost, settings.relayWsPort, settings.relayWsPath);
                webSocket.onEvent(webSocketEvent);
                firstRun = false;
          }
          webSocket.loop();
          if (webSocket.isConnected()) {
            Serial.println("--- connected ---");
            changeState(STATE_RELAY_RUNNING);
          }
          break;
        }

        case STATE_RELAY_RUNNING: {
            if (webSocket.isConnected()) {
                webSocket.loop();
            } else {
                changeState(STATE_CONNECTING_TO_RELAY);
            }
            break;

        }

        case SOFT_AP_ON:
            atemSwitcher.runLoop();
            break;

        case STATE_SWITCHER_RUNNING: {
            //Handle data exchange and connection to swithcher
            atemSwitcher.runLoop();

            int tallySources = atemSwitcher.getTallyByIndexSources();
            
            //Set LED color accordingly
            int color = getLedColor(settings.tallyNumber);
            setLedColor(color);
           
            //Switch state if ATEM connection is lost...
            if (!atemSwitcher.isConnected()) { 
                Serial.println("------------------------");
                Serial.println("Connection to Switcher lost...");
                changeState(STATE_CONNECTING_TO_SWITCHER);

            }
            
            break;
        }
    } 

    //Switch state if WiFi connection is lost...
    if (WiFi.status() != WL_CONNECTED && state != STATE_CONNECTING_TO_WIFI && state != SOFT_AP_ON) {
        Serial.println("------------------------");
        Serial.println("WiFi connection lost...");
        changeState(STATE_CONNECTING_TO_WIFI);
        //Force atem library to reset connection, in order for status to read correctly on website.
        atemSwitcher.begin(settings.switcherIP);
        atemSwitcher.connect();
    }

    //Handle web interface
    server.handleClient();

    //monitor battery and button
    // Serial.println("=LOOP=");

    // batteryLoop();
    buttonLoop();

    // Serial.println("======FREE HEAP========");
    // Serial.println(ESP.getFreeHeap());
    //delay(100);
}

//Handle the change of states in the program
void changeState(uint8_t stateToChangeTo) {
    Serial.println("------------------------");
    Serial.println("state change...");
    firstRun = true;
    switch (stateToChangeTo) {
        case STATE_CONNECTING_TO_WIFI:
            state = STATE_CONNECTING_TO_WIFI;
            setLedColor(LED_BLUE);
            break;
        case STATE_CONNECTING_TO_SWITCHER:
            state = STATE_CONNECTING_TO_SWITCHER;
            setLedColor(LED_PINK);
            break;
        case STATE_CONNECTING_TO_RELAY:
            state = STATE_CONNECTING_TO_RELAY;
            setLedColor(LED_PINK);
            break;
        case STATE_SWITCHER_RUNNING:
            state = STATE_SWITCHER_RUNNING;
            setLedColor(LED_ORANGE);
            break;
        case STATE_RELAY_RUNNING:
            state = STATE_RELAY_RUNNING;
            setLedColor(LED_ORANGE);
            break;
        case SOFT_AP_ON:
            state = SOFT_AP_ON;
            setLedColor(LED_WHITE);
            firstRun = false;
            break;

    }
}

void setLedColor(uint8_t color) {
    setLED(color, PIN_RED1, PIN_GREEN1, PIN_BLUE1);
}


// //Set the color of a LED using the given pins
void setLED(uint8_t color, int pinRed, int pinGreen, int pinBlue) {
    uint8_t ledBrightness = settings.ledBrightness;
    void (*writeFunc)(uint8_t, uint8_t);
    if(ledBrightness >= 0xff) {
        writeFunc = &digitalWrite;
        ledBrightness = 1;
    } else {
        writeFunc = &analogWriteWrapper;
    }

    switch (color) {
        case LED_OFF:
            Serial.println("LED OFF");
            digitalWrite(pinRed, 0);
            digitalWrite(pinGreen, 0);
            digitalWrite(pinBlue, 0);
            break;
        case LED_RED:
            writeFunc(pinRed, ledBrightness);
            digitalWrite(pinGreen, 0);
            digitalWrite(pinBlue, 0);
            break;
        case LED_GREEN:
            digitalWrite(pinRed, 0);
            writeFunc(pinGreen, ledBrightness);
            digitalWrite(pinBlue, 0);
            break;
        case LED_BLUE:
            digitalWrite(pinRed, 0);
            digitalWrite(pinGreen, 0);
            writeFunc(pinBlue, ledBrightness);
            break;
        case LED_YELLOW:
            writeFunc(pinRed, ledBrightness);
            writeFunc(pinGreen, ledBrightness);
            digitalWrite(pinBlue, 0);
            break;
        case LED_PINK:
            writeFunc(pinRed, ledBrightness);
            digitalWrite(pinGreen, 0);
            writeFunc(pinBlue, ledBrightness);
            break;
        case LED_WHITE:
            writeFunc(pinRed, ledBrightness);
            writeFunc(pinGreen, ledBrightness);
            writeFunc(pinBlue, ledBrightness);
            break;
    }

}

void analogWriteWrapper(uint8_t pin, uint8_t value) {
    analogWrite(pin, value);
}


int getTallyState(uint16_t tallyNo) {

    if(tallyNo >= atemSwitcher.getTallyByIndexSources()) { //out of range
        return TALLY_FLAG_OFF;
    }

    uint8_t tallyFlag = atemSwitcher.getTallyByIndexTallyFlags(tallyNo);

    if (tallyFlag & TALLY_FLAG_PROGRAM) {
        return TALLY_FLAG_PROGRAM;
    } else if (tallyFlag & TALLY_FLAG_PREVIEW) {
        return TALLY_FLAG_PREVIEW;
    } else {
        return TALLY_FLAG_OFF;
    }
}


int getLedColor(int tallyNo) {

    int tallyState = getTallyState(tallyNo);

    if (tallyState == TALLY_FLAG_PROGRAM) {   //if tally live        
        return LED_RED;
    } 
    else if (tallyState == TALLY_FLAG_PREVIEW) { //if tally preview
        return LED_GREEN;          
    } else {                                            
        return LED_OFF;   //if tally is neither
    }
}


//Serve setup web page to client, by sending HTML with the correct variables
void handleRoot() {
    String html = "<!DOCTYPE html><html><head><meta charset=\"ASCII\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\"><title>Tally Light setup</title></head><script>function switchIpField(e){console.log(\"switch\");console.log(e);var target=e.srcElement||e.target;var maxLength=parseInt(target.attributes[\"maxlength\"].value,10);var myLength=target.value.length;if(myLength>=maxLength){var next=target.nextElementSibling;if(next!=null){if(next.className.includes(\"IP\")){next.focus();}}}else if(myLength==0){var previous=target.previousElementSibling;if(previous!=null){if(previous.className.includes(\"IP\")){previous.focus();}}}}function ipFieldFocus(e){console.log(\"focus\");console.log(e);var target=e.srcElement||e.target;target.select();}function load(){var containers=document.getElementsByClassName(\"IP\");for(var i=0;i<containers.length;i++){var container=containers[i];container.oninput=switchIpField;container.onfocus=ipFieldFocus;}containers=document.getElementsByClassName(\"tIP\");for(var i=0;i<containers.length;i++){var container=containers[i];container.oninput=switchIpField;container.onfocus=ipFieldFocus;}toggleStaticIPFields();toggleRelayServerFields();}function toggleStaticIPFields(){var enabled=document.getElementById(\"staticIP\").checked;document.getElementById(\"staticIPHidden\").disabled=enabled;var staticIpFields=document.getElementsByClassName('tIP');for(var i=0;i<staticIpFields.length;i++){staticIpFields[i].disabled=!enabled;}}function toggleRelayServerFields(){var enabled=document.getElementById(\"relayServer\").checked;document.getElementById(\"relayServerHidden\").disabled=enabled;var relayServerHost=document.getElementById('relayServerHost');relayServerHost.disabled=!enabled;var relayServerPath=document.getElementById('relayServerPath');relayServerPath.disabled=!enabled;var relayServerPort=document.getElementById('relayServerPort');relayServerPort.disabled=!enabled;var aIPFields=document.getElementsByClassName('IP');for(var i=0;i<aIPFields.length;i++){aIPFields[i].disabled=enabled;}} </script><style>a{color:#0F79E0}</style><body style=\"font-family:Verdana;white-space:nowrap;\" onload=\"load()\"><table cellpadding=\"2\" style=\"width:100%\"><tr bgcolor=\"#777777\" style=\"color:#ffffff;font-size:.8em;\"><td colspan=\"3\"><h1>&nbsp;" + (String)DISPLAY_NAME + " setup</h1><h2>&nbsp;Status:</h2></td></tr><tr><td><br></td><td></td><td style=\"width:100%;\"></td></tr><tr><td>Connection Status:</td><td colspan=\"2\">";
    switch (WiFi.status()) {
        case WL_CONNECTED:
            html += "Connected to network";
            break;
        case WL_NO_SSID_AVAIL:
            html += "Network not found";
            break;
        case WL_CONNECT_FAILED:
            html += "Invalid password";
            break;
        case WL_IDLE_STATUS:
            html += "Changing state...";
            break;
        case WL_DISCONNECTED:
            html += "Station mode disabled";
            break;
        case -1:
            html += "Timeout";
            break;
    }
    html += "</td></tr><tr><td>Network name (SSID):</td><td colspan=\"2\">";
    html += getSSID();
    html += "</td></tr><tr><td><br></td></tr><tr><td>Signal strength:</td><td colspan=\"2\">";
    html += WiFi.RSSI();
    html += " dBm</td></tr>";
    // Commented out for users without batteries
    html += "<tr><td>Battery voltage:</td><td colspan=\"2\">";
    html += dtostrf(uBatt, 0, 3, buffer);
    html += " V</td></tr>";
    html += "<tr><td><br></td></tr><tr><td>Static IP:</td><td colspan=\"2\">";
    html += settings.staticIP == true ? "True" : "False";
    html += "</td></tr><tr><td>" + (String)DISPLAY_NAME + " IP:</td><td colspan=\"2\">";
    html += WiFi.localIP().toString();
    html += "</td></tr><tr><td>Subnet mask: </td><td colspan=\"2\">";
    html += WiFi.subnetMask().toString();
    html += "</td></tr><tr><td>Gateway: </td><td colspan=\"2\">";
    html += WiFi.gatewayIP().toString();
    html += "</td></tr><tr><td><br></td></tr>";
    if (settings.useRelayServer) {
        html += "<tr><td>Relay server status:</td><td colspan=\"2\">";
        if (state == STATE_CONNECTING_TO_RELAY) html += "Trying to connect to relay server...";
        else if (state  == STATE_RELAY_RUNNING) html += "Connected and running"; 
        
        html += "</td></tr><tr><td>Relay server adress:</td><td colspan=\"2\">";
        html += settings.relayWsHost;
        html += settings.relayWsPath;
        html += "</td></tr><tr><td><br></td></tr>";
    }
    else {
        html += "<tr><td>ATEM switcher status:</td><td colspan=\"2\">";
        // if (atemSwitcher.hasInitialized())
        //     html += "Connected - Initialized";
        // else
        if (atemSwitcher.isRejected())
            html += "Connection rejected - No empty spot";
        else if (atemSwitcher.isConnected())
            html += "Connected"; // - Wating for initialization";
        else if (WiFi.status() == WL_CONNECTED)
            html += "Disconnected - No response from switcher";
        else
            html += "Disconnected - Waiting for WiFi";
        
        html += "</td></tr><tr><td>ATEM switcher IP:</td><td colspan=\"2\">";
        html += (String)settings.switcherIP[0] + '.' + settings.switcherIP[1] + '.' + settings.switcherIP[2] + '.' + settings.switcherIP[3];
        html += "</td></tr><tr><td><br></td></tr>";
    }

    html += "<tr bgcolor=\"#777777\" style=\"color:#ffffff;font-size:.8em;\"><td colspan=\"3\"><h2>&nbsp;Settings:</h2></td></tr><tr><td><br></td></tr><form action=\"/save\" method=\"post\"><tr><td>Tally Light name: </td><td><input type=\"text\" size=\"30\" maxlength=\"30\" name=\"tName\" value=\"";
    html += WiFi.hostname();
    html += "\" required/></td></tr><tr><td><br></td></tr><tr><td>Tally Light number: </td><td><input type=\"number\" size=\"5\" min=\"1\" max=\"41\" name=\"tNo\" value=\"";
    html += (settings.tallyNumber + 1);
    html += "\" required/></td></tr><tr><td>Led brightness: </td><td><input type=\"number\" size=\"5\" min=\"0\" max=\"255\" name=\"ledBright\" value=\"";
    html += settings.ledBrightness;
    html += "\" required/></td></tr><tr><td><br></td></tr><tr><td>Network name(SSID): </td><td><input type=\"text\" size=\"30\" maxlength=\"30\" name=\"ssid\" value=\"";
    html += getSSID();
    html += "\" required/></td></tr><tr><td>Network password: </td><td><input type=\"password\" size=\"30\" maxlength=\"30\" name=\"pwd\" pattern=\"^$|.{1,32}\" value=\"";
    html += WiFi.psk();
    html += "\"/></td></tr><tr><td><br></td></tr><tr><td>Use static IP: </td><td><input type=\"hidden\" id=\"staticIPHidden\" name=\"staticIP\" value=\"false\"/><input id=\"staticIP\" type=\"checkbox\" name=\"staticIP\" value=\"true\" onchange=\"toggleStaticIPFields()\"";
    if (settings.staticIP)
        html += " checked";
    html += "/></td></tr><tr><td>" + (String)DISPLAY_NAME + " IP: </td><td><input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"tIP1\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallyIP[0];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"tIP2\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallyIP[1];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"tIP3\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallyIP[2];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"tIP4\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallyIP[3];
    html += "\" required/></td></tr><tr><td>Subnet mask: </td><td><input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"subIP1\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallySubnetMask[0];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"subIP2\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallySubnetMask[1];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"subIP3\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallySubnetMask[2];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"subIP4\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallySubnetMask[3];
    html += "\" required/></td></tr><tr><td>Gateway: </td><td><input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"gwIP1\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallyGateway[0];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"gwIP2\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallyGateway[1];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"gwIP3\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallyGateway[2];
    html += "\" required/>. <input class=\"tIP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"gwIP4\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.tallyGateway[3];
    html += "\" required/></td></tr><tr><td><br></td></tr><tr><td>Use Relay Server: </td><td><input type=\"hidden\" id=\"relayServerHidden\" name=\"relayServer\" value=\"false\"/><input id=\"relayServer\" type=\"checkbox\" name=\"relayServer\" value=\"true\" onchange=\"toggleRelayServerFields()\"";
    if (settings.useRelayServer)
        html += " checked";
    html += "/></td></tr><tr><td>Relay WebSocket Host: </td><td><input id=\"relayServerHost\" type=\"text\" size=\"30\" maxlength=\"30\" name=\"relayServerHost\" value=\"";
    html += settings.relayWsHost;
    html += "\"";
    if (!settings.useRelayServer)
        html += " disabled";
    html += "/></td></tr><tr><td>Relay WebSocket Path: </td><td><input id=\"relayServerPath\" type=\"text\" size=\"30\" maxlength=\"30\" name=\"relayServerPath\" value=\"";
    html += settings.relayWsPath;
    html += "\"";
    if (!settings.useRelayServer)
        html += " disabled";
    html += "/></td></tr><tr><td>Relay WebSocket Port: </td><td><input id=\"relayServerPort\" type=\"number\" size=\"5\" min=\"1\" max=\"65535\" name=\"relayServerPort\" value=\"";
    html += settings.relayWsPort;
    html += "\"";
    if (!settings.useRelayServer)
        html += " disabled";
    html += "/></td></tr><tr><td><br></td></tr><tr><td>ATEM switcher IP: </td><td><input class=\"IP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"aIP1\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.switcherIP[0];
    html += "\"";
    if (settings.useRelayServer)
        html += " disabled";
    html += "/>. <input class=\"IP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"aIP2\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.switcherIP[1];
    html += "\"";
    if (settings.useRelayServer)
        html += " disabled";
    html += "/>. <input class=\"IP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"aIP3\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.switcherIP[2];
    html += "\"";
    if (settings.useRelayServer)
        html += " disabled";
    html += "/>. <input class=\"IP\" type=\"text\" size=\"3\" maxlength=\"3\" name=\"aIP4\" pattern=\"\\d{0,3}\" value=\"";
    html += settings.switcherIP[3];
    html += "\"";
    if (settings.useRelayServer)
    html += " disabled";
    html += "/></td></tr><tr><td><br></td></tr><tr><td/><td style=\"float: right;\"><input type=\"submit\" value=\"Save Changes\"/></td></tr></form><tr bgcolor=\"#cccccc\" style=\"font-size: .8em;\"><td colspan=\"3\"><p>&nbsp;&copy; Modified by <a href=\"https://github.com/pam-param-pam/\">Pam</a>, made by <a href=\"https://aronhetlam.github.io/\">Aron N. Het Lam</a></p><p>&nbsp;Based on ATEM libraries for Arduino by <a href=\"https://www.skaarhoj.com/\">SKAARHOJ</a></p></td></tr></table></body></html>";
    server.send(200, "text/html", html);

    

}

//Save new settings from client in EEPROM and restart the ESP8266 module
void handleSave() {
    if (server.method() != HTTP_POST) {
        server.send(405, "text/html", "<!DOCTYPE html><html><head><meta charset=\"ASCII\"><meta name=\"viewport\"content=\"width=device-width, initial-scale=1.0\"><title>Tally Light setup</title></head><body style=\"font-family:Verdana;\"><table bgcolor=\"#777777\"border=\"0\"width=\"100%\"cellpadding=\"1\"style=\"color:#ffffff;font-size:.8em;\"><tr><td><h1>&nbsp;" +
    (String)DISPLAY_NAME +
    " setup</h1></td></tr></table><br>Request without posting settings not allowed</body></html>");
    } else {
        String ssid;
        String pwd;
        bool change = false;
        for (uint8_t i = 0; i < server.args(); i++) {
            change = true;
            String var = server.argName(i);
            String val = server.arg(i);

            if (var == "tName") {
                val.toCharArray(settings.tallyName, (uint8_t)32);
            } else if (var == "tNo") {
                settings.tallyNumber = val.toInt() - 1;
            } else if (var == "ledBright") {
                settings.ledBrightness = val.toInt();
            } else if (var == "ssid") {
                ssid = String(val);
            } else if (var == "pwd") {
                pwd = String(val);
            } else if (var == "staticIP") {
                settings.staticIP = (val == "true");
            } else if (var == "tIP1") {
                settings.tallyIP[0] = val.toInt();
            } else if (var == "tIP2") {
                settings.tallyIP[1] = val.toInt();
            } else if (var == "tIP3") {
                settings.tallyIP[2] = val.toInt();
            } else if (var == "tIP4") {
                settings.tallyIP[3] = val.toInt();
            } else if (var == "mask1") {
                settings.tallySubnetMask[0] = val.toInt();
            } else if (var == "mask2") {
                settings.tallySubnetMask[1] = val.toInt();
            } else if (var == "mask3") {
                settings.tallySubnetMask[2] = val.toInt();
            } else if (var == "mask4") {
                settings.tallySubnetMask[3] = val.toInt();
            } else if (var == "gate1") {
                settings.tallyGateway[0] = val.toInt();
            } else if (var == "gate2") {
                settings.tallyGateway[1] = val.toInt();
            } else if (var == "gate3") {
                settings.tallyGateway[2] = val.toInt();
            } else if (var == "gate4") {
                settings.tallyGateway[3] = val.toInt();
            } else if (var == "aIP1") {
                settings.switcherIP[0] = val.toInt();
            } else if (var == "aIP2") {
                settings.switcherIP[1] = val.toInt();
            } else if (var == "aIP3") {
                settings.switcherIP[2] = val.toInt();
            } else if (var == "aIP4") {
                settings.switcherIP[3] = val.toInt();
            } else if (var == "relayServer") {
                settings.useRelayServer = (val == "true");
            } else if (var == "relayServerHost") {
                val.toCharArray(settings.relayWsHost, (uint8_t)64);
            } else if (var == "relayServerPath") {
                val.toCharArray(settings.relayWsPath, (uint8_t)32);
            } else if (var == "relayServerPort") {
                settings.relayWsPort = val.toInt();
            }
        }

        if (change) {
            EEPROM.put(0, settings);
            EEPROM.commit();

            server.send(200, "text/html", (String)"<!DOCTYPE html><html><head><meta charset=\"ASCII\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"><title>Tally Light setup</title></head><body><table bgcolor=\"#777777\" border=\"0\" width=\"100%\" cellpadding=\"1\" style=\"font-family:Verdana;color:#ffffff;font-size:.8em;\"><tr><td><h1>&nbsp;" +
            (String)DISPLAY_NAME +
            " setup</h1></td></tr></table><br>Settings saved successfully.<br><br><form action=\"/\"><button type=\"submit\">Go Back</button></form></body></html>");

            // Delay to let data be saved, and the response to be sent properly to the client
            server.close(); // Close server to flush and ensure the response gets to the client
            delay(100);

            // Change into STA mode to disable softAP
            //WiFi.mode(WIFI_STA);
            delay(100); // Give it time to switch over to STA mode (this is important on the ESP32 at least)
            //Serial.println("LEN");
            //Serial.println(strlen(pwd));
            if (ssid && pwd) {
                WiFi.persistent(true); // Needed by ESP8266
                Serial.println("PASSWORD");
                Serial.println(pwd);
                // Pass in 'false' as 5th (connect) argument so we don't waste time trying to connect, just save the new SSID/PSK
                // 3rd argument is channel - '0' is default. 4th argument is BSSID - 'NULL' is default.
                WiFi.begin(ssid.c_str(), pwd.c_str(), 0, NULL, false);
            }

            //Delay to apply settings before restart
            delay(100);
            ESP.restart();
        }
    }
}

//Send 404 to client in case of invalid webpage being requested.
void handleNotFound() {
    server.send(404, "text/html", "<!DOCTYPE html><html><head><meta charset=\"ASCII\"><meta name=\"viewport\"content=\"width=device-width, initial-scale=1.0\"><title>" +
    (String)DISPLAY_NAME +
    " setup</title></head><body style=\"font-family:Verdana;\"><table bgcolor=\"#777777\"border=\"0\"width=\"100%\"cellpadding=\"1\"style=\"color:#ffffff;font-size:.8em;\"><tr><td><h1>&nbsp Tally Light setup</h1></td></tr></table><br>404 - Page not found</body></html>");
}

String getSSID() {
    return WiFi.SSID();
}

void buttonLoop() {

    buttonReading = digitalRead(BUTTON_PIN);
    // Serial.println("buttonReading");
    // Serial.println(buttonReading);

    if (buttonReading != buttonPrevious) {
      if (buttonReading == HIGH) {
        webSocket.disconnect();
        changeState(SOFT_AP_ON);
        Serial.println("ACCESS POINT IS ON");
        WiFi.mode(WIFI_AP_STA); 
        WiFi.softAP((String)settings.tallyName + " setup");
      }
      else {
        WiFi.mode(WIFI_STA); 
        Serial.println("ACCESS POINT IS OFF");
        changeState(STATE_CONNECTING_TO_WIFI);
      }

    buttonPrevious = buttonReading;
    }
}


void batteryLoop() {
  unsigned long batteryLoopStartTime = millis();
  batteryElapsedTime = batteryLoopStartTime - baterryStartTime;
  int raw = analogRead(A0);
  uBatt = (double)raw / 1023 * 4.2;
  if (uBatt <= 3.600) {
    unsigned int interval = 500;
    if (uBatt <= 3.300) interval = 100;
  
    if ((batteryElapsedTime >= interval)) { 
      betteryLedState = (betteryLedState == HIGH) ? LOW : HIGH;

      digitalWrite(LED_BUILTIN2, betteryLedState);
      baterryStartTime = batteryLoopStartTime;
    }
   
  }                  
  Serial.println("uBatt");

  Serial.println(uBatt);

  // if(uBatt <= 3.499 && uBatt > 0.1) {
  //     Serial.println("ENTERING DEEP SLEEP");
  //     setBothLEDs(LED_OFF);
  //     delay(100);
  //     ESP.deepSleep(0, WAKE_NO_RFCAL);
  // }

       
}

