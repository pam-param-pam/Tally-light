#include "SettingsStore.h"
#include <EEPROM.h>
#include <ESP8266WiFi.h>

Settings settings;

void loadSettings() {
    EEPROM.begin(sizeof(Settings));
    EEPROM.get(0, settings);
    // EEPROM can contain interrupted writes; bound every stored string.
    settings.relayWsHost[sizeof(settings.relayWsHost) - 1] = '\0';
    settings.relayWsPath[sizeof(settings.relayWsPath) - 1] = '\0';
    settings.relayToken[sizeof(settings.relayToken) - 1] = '\0';
    settings.wifiSsid[sizeof(settings.wifiSsid) - 1] = '\0';
    settings.wifiPassword[sizeof(settings.wifiPassword) - 1] = '\0';
    settings.tallyName[sizeof(settings.tallyName) - 1] = '\0';
    if (settings.layoutId != SETTINGS_LAYOUT) {
        settings = Settings{};
        settings.layoutId = SETTINGS_LAYOUT;
        settings.ledBrightness = 255;
        static_assert(sizeof("Tally Light") <= sizeof(settings.tallyName),
                      "Default tally name must fit in settings");
        memcpy(settings.tallyName, "Tally Light", sizeof("Tally Light"));
        saveSettings();
    }
}

bool saveSettings() {
    EEPROM.put(0, settings);
    return EEPROM.commit();
}

bool relayConfigured() {
    return settings.relayWsHost[0] != '\0' && settings.relayWsPort != 0 && settings.relayToken[0] != '\0';
}

bool settingsConfigured() {
    if (!settings.wifiSsid[0] || !settings.wifiPassword[0]) return false;
    return relayConfigured();
}

String deviceId() {
    return "tl-" + String(ESP.getChipId(), HEX);
}

String relayUrl() {
    if (!relayConfigured()) return "";
    String url = settings.relayWsSecure ? "wss://" : "ws://";
    url += settings.relayWsHost;
    if (settings.relayPortExplicit) {
        url += ":";
        url += settings.relayWsPort;
    }
    url += settings.relayWsPath;
    return url;
}

bool parseRelayUrl(String url, Settings &target) {
    String original = url;
    url.trim();
    if (url != original) return false;
    if (url.length() == 0) {
        target.relayWsHost[0] = '\0';
        target.relayWsPath[0] = '\0';
        target.relayWsPort = 0;
        target.relayPortExplicit = false;
        return true;
    }
    bool secure;
    if (url.startsWith("wss://")) {
        secure = true;
        url.remove(0, 6);
    } else if (url.startsWith("ws://")) {
        secure = false;
        url.remove(0, 5);
    } else {
        return false;
    }
    int slash = url.indexOf('/');
    if (slash < 0) return false;
    String hostPort = url.substring(0, slash);
    String path = url.substring(slash);
    int colon = hostPort.lastIndexOf(':');
    String host = colon < 0 ? hostPort : hostPort.substring(0, colon);
    String portText = colon < 0 ? "" : hostPort.substring(colon + 1);
    if (host.length() == 0 || host.length() >= sizeof(target.relayWsHost) ||
        path != "/ws/lights" || path.length() >= sizeof(target.relayWsPath) ||
        host.indexOf('@') >= 0 || host.indexOf(' ') >= 0 || host.indexOf('?') >= 0 ||
        host.indexOf('#') >= 0 || host.indexOf('[') >= 0 || host.indexOf(']') >= 0)
        return false;
    uint32_t port = secure ? 443 : 80;
    if (colon >= 0) {
        if (portText.length() == 0 || portText.length() > 5) return false;
        for (unsigned int i = 0; i < portText.length(); ++i)
            if (!isDigit(portText[i])) return false;
        port = portText.toInt();
        if (port == 0 || port > 65535) return false;
    }
    host.toCharArray(target.relayWsHost, sizeof(target.relayWsHost));
    path.toCharArray(target.relayWsPath, sizeof(target.relayWsPath));
    target.relayWsPort = port;
    target.relayWsSecure = secure;
    target.relayPortExplicit = colon >= 0;
    return true;
}

const char *stageUsbSettings(JsonObject changes, Settings &next) {
    if (changes.size() == 0) return "data";
    for (JsonPair item: changes) {
        String key = item.key().c_str();
        JsonVariant value = item.value();
        if (key == "name") {
            if (!value.is<const char *>()) return "name";
            String name = value.as<String>();
            if (name.length() == 0 || name.length() > 30) return "name";
            name.toCharArray(next.tallyName, sizeof(next.tallyName));
        } else if (key == "source") {
            if (!value.is<int>() || value.as<int>() < 1 || value.as<int>() > 255) return "source";
            next.tallyNumber = value.as<int>() - 1;
        } else if (key == "brightness") {
            if (!value.is<int>() || value.as<int>() < 0 || value.as<int>() > 255) return "brightness";
            next.ledBrightness = value.as<int>();
        } else if (key == "relay") {
            if (!value.is<JsonObject>() || value.as<JsonObject>().size() == 0) return "relay";
            for (JsonPair part: value.as<JsonObject>()) {
                String field = part.key().c_str();
                JsonVariant selected = part.value();
                if (field == "url") {
                    if (!selected.is<const char *>() || selected.as<String>().length() == 0)
                        return "relay.url";
                    if (!parseRelayUrl(selected.as<String>(), next)) return "relay.url";
                } else if (field == "token") {
                    if (!selected.is<const char *>()) return "relay.token";
                    String token = selected.as<String>();
                    if (token.length() < 32 || token.length() > 63) return "relay.token";
                    token.toCharArray(next.relayToken, sizeof(next.relayToken));
                } else return "relay";
            }
        } else if (key == "wifi") {
            if (!value.is<JsonObject>() || value.as<JsonObject>().size() == 0) return "wifi";
            for (JsonPair part: value.as<JsonObject>()) {
                String field = part.key().c_str();
                JsonVariant selected = part.value();
                if (field == "ssid") {
                    if (!selected.is<const char *>()) return "wifi.ssid";
                    String ssid = selected.as<String>();
                    if (ssid.length() == 0 || ssid.length() > 32) return "wifi.ssid";
                    ssid.toCharArray(next.wifiSsid, sizeof(next.wifiSsid));
                } else if (field == "password") {
                    if (!selected.is<const char *>()) return "wifi.password";
                    String password = selected.as<String>();
                    if (password.length() == 0 || password.length() > 63) return "wifi.password";
                    password.toCharArray(next.wifiPassword, sizeof(next.wifiPassword));
                } else return "wifi";
            }
        } else return "data";
    }
    return nullptr;
}
