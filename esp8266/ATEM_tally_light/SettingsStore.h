#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <type_traits>

struct Settings {
    char relayWsHost[64] = "";
    char relayWsPath[32] = "";
    char relayToken[64] = "";
    char wifiSsid[33];
    char wifiPassword[64];
    uint16_t relayWsPort;
    char tallyName[32] = "";
    uint8_t tallyNumber;
    uint8_t ledBrightness;
    bool relayWsSecure;
    bool relayPortExplicit;
    uint32_t layoutId;
};
static_assert(std::is_trivially_copyable<Settings>::value,
"EEPROM settings must contain plain data only");

extern Settings settings;
constexpr uint32_t
SETTINGS_LAYOUT = 0x544C320A;

void loadSettings();

bool saveSettings();

bool relayConfigured();

bool settingsConfigured();

String deviceId();

String relayUrl();

bool parseRelayUrl(String url, Settings &target);

const char *stageUsbSettings(JsonObject changes, Settings &next);

