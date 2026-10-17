#pragma once

#include <Arduino.h>

enum class DiodeState : uint8_t {
    Standby,
    Program,
    Preview,
    NoSignal,
    ConnectingWifi,
    ConnectingRelay,
};

void setupDiode();
void setDiodeState(DiodeState state);
void refreshDiode();
