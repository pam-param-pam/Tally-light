#include "Diode.h"
#include "SettingsStore.h"

#ifndef PIN_RED1
#define PIN_RED1 0
#endif
#ifndef PIN_GREEN1
#define PIN_GREEN1 5
#endif
#ifndef PIN_BLUE1
#define PIN_BLUE1 13
#endif

namespace {
    constexpr uint8_t LED_BUILTIN2 = 16;
    enum class Color : uint8_t { Off, Red, Green, Blue, Yellow, Pink };

    DiodeState currentState = DiodeState::Standby;

    Color stateColor(DiodeState state) {
        switch (state) {
            case DiodeState::Program: return Color::Red;
            case DiodeState::Preview: return Color::Green;
            case DiodeState::NoSignal: return Color::Yellow;
            case DiodeState::ConnectingWifi: return Color::Blue;
            case DiodeState::ConnectingRelay: return Color::Pink;
            case DiodeState::Standby: return Color::Off;
        }
        return Color::Off;
    }

    void writePin(uint8_t pin, bool enabled) {
        if (!enabled) {
            digitalWrite(pin, LOW);
        } else if (settings.ledBrightness == 255) {
            digitalWrite(pin, HIGH);
        } else {
            analogWrite(pin, settings.ledBrightness);
        }
    }

    void writeColor(Color color) {
        writePin(PIN_RED1, color == Color::Red || color == Color::Yellow || color == Color::Pink);
        writePin(PIN_GREEN1, color == Color::Green || color == Color::Yellow);
        writePin(PIN_BLUE1, color == Color::Blue || color == Color::Pink);
    }

    void render() {
        writeColor(stateColor(currentState));
    }
}

void setupDiode() {
    pinMode(LED_BUILTIN, OUTPUT);
    pinMode(LED_BUILTIN2, OUTPUT);
    pinMode(PIN_RED1, OUTPUT);
    pinMode(PIN_GREEN1, OUTPUT);
    pinMode(PIN_BLUE1, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);
    digitalWrite(LED_BUILTIN2, HIGH);
    pinMode(A0, INPUT);
    writeColor(Color::Off);
}

void setDiodeState(DiodeState state) {
    currentState = state;
    render();
}

void refreshDiode() {
    render();
}
