#include "SettingsJson.h"
#include "SettingsStore.h"
#include <ESP8266WiFi.h>

void fillSettingsJson(JsonObject saved, bool includeRelayToken) {
    saved["name"] = settings.tallyName;
    saved["source"] = settings.tallyNumber + 1;
    saved["brightness"] = settings.ledBrightness;
    JsonObject relay = saved["relay"].to<JsonObject>();
    if (relayConfigured()) relay["url"] = relayUrl();
    else relay["url"] = nullptr;
    if (includeRelayToken) relay["token"] = settings.relayToken;
    JsonObject wifi = saved["wifi"].to<JsonObject>();
    wifi["ssid"] = settings.wifiSsid;
    wifi["password"] = settings.wifiPassword;
}
