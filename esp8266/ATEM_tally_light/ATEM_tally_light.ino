#include "SettingsStore.h"
#include "UsbSetup.h"
#include "RelayClient.h"
#include "Diode.h"
#include <ESP8266WiFi.h>

enum class State : uint8_t {
    ConnectingToWifi,
    ConnectingToRelay,
    RelayRunning
};

State state = State::ConnectingToWifi;

void changeState(State nextState);

void setup() {
    // Reserve enough UART space for a complete setup.set JSON frame.
    Serial.setRxBufferSize(2304);
    Serial.begin(115200);
    Serial.setDebugOutput(false);
    loadSettings();
    setupDiode();
    WiFi.mode(WIFI_STA);
    WiFi.hostname(deviceId());
    WiFi.setAutoReconnect(true);
    WiFi.persistent(false);
    WiFi.begin(settings.wifiSsid, settings.wifiPassword);
    changeState(State::ConnectingToWifi);
}

void loop() {
    handleSerial();
    switch (state) {
        case State::ConnectingToWifi:
            if (WiFi.status() == WL_CONNECTED)
                changeState(State::ConnectingToRelay);
            break;
        case State::ConnectingToRelay:
            if (relayConnected()) changeState(State::RelayRunning);
            break;
        case State::RelayRunning:
            if (!relayConnected()) changeState(State::ConnectingToRelay);
            break;
    }

    if (WiFi.status() == WL_CONNECTED) serviceRelay();

    if (WiFi.status() != WL_CONNECTED && state != State::ConnectingToWifi) {
        stopRelay();
        changeState(State::ConnectingToWifi);
    }
    delay(100);
}

void changeState(State nextState) {
    state = nextState;
    switch (nextState) {
        case State::ConnectingToWifi:
            setDiodeState(DiodeState::ConnectingWifi);
            break;
        case State::ConnectingToRelay:
            setDiodeState(DiodeState::ConnectingRelay);
            break;
        case State::RelayRunning:
            setDiodeState(DiodeState::NoSignal);
            break;
    }
}
