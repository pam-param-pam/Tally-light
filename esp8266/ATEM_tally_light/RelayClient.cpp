#include "RelayClient.h"
#include "SettingsStore.h"
#include "SettingsJson.h"
#include "Diode.h"
#include <ESP8266WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

namespace {
    WebSocketsClient webSocket;
    bool relayWelcomed = false;
    bool relayStarted = false;
}

void webSocketEvent(WStype_t type, uint8_t *payload, size_t length);

void startRelay() {
    if (relayStarted || !relayConfigured() || WiFi.status() != WL_CONNECTED) return;
    if (settings.relayWsSecure)
        webSocket.beginSSL(settings.relayWsHost, settings.relayWsPort, settings.relayWsPath);
    else
        webSocket.begin(settings.relayWsHost, settings.relayWsPort, settings.relayWsPath);
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
    relayStarted = true;
}

void sendJson(JsonDocument &doc) {
    String json;
    serializeJson(doc, json);
    webSocket.sendTXT(json);
}

void sendHello() {
    JsonDocument doc;
    doc["type"] = "hello";
    doc["id"] = String(millis());
    doc["deviceId"] = deviceId();
    doc["data"]["token"] = settings.relayToken;
    fillSettingsJson(doc["data"]["settings"].to<JsonObject>(), false);
    sendJson(doc);
}

void sendSettingsResult(const char *requestId, const char *state, const char *field = nullptr) {
    JsonDocument response;
    response["type"] = "settings.result";
    response["id"] = String(millis());
    response["replyTo"] = requestId;
    response["deviceId"] = deviceId();
    response["data"]["state"] = state;
    if (field) response["data"]["field"] = field;
    sendJson(response);
}

void applySettings(JsonDocument &doc) {
    String requestId = doc["id"].as<String>();
    JsonObject changes = doc["data"].as<JsonObject>();
    if (requestId.length() == 0 || changes.isNull() || changes.size() == 0) {
        sendSettingsResult(requestId.c_str(), "rejected", "data");
        return;
    }

    Settings next = settings;
    bool restart = false;
    bool wifiSsidSpecified = false;
    String requestedWifiSsid;
    const char *invalid = nullptr;

    for (JsonPair item: changes) {
        String key = item.key().c_str();
        JsonVariant value = item.value();
        if (key == "name") {
            if (!value.is<const char *>()) {
                invalid = "name";
                break;
            }
            String name = value.as<String>();
            if (name.length() == 0 || name.length() > 30) invalid = "name";
            else if (name != settings.tallyName) {
                name.toCharArray(next.tallyName, sizeof(next.tallyName));
                restart = true;
            }
        } else if (key == "source") {
            if (!value.is<int>() || value.as<int>() < 1 || value.as<int>() > 255) invalid = "source";
            else if (value.as<int>() != settings.tallyNumber + 1) {
                next.tallyNumber = value.as<int>() - 1;
                restart = true;
            }
        } else if (key == "brightness") {
            if (!value.is<int>() || value.as<int>() < 0 || value.as<int>() > 255) invalid = "brightness";
            else next.ledBrightness = value.as<int>();
        } else if (key == "relay") {
            if (!value.is<JsonObject>() || value.as<JsonObject>().size() != 1 ||
                !value.as<JsonObject>().containsKey("url")) {
                invalid = "relay";
                break;
            }
            JsonVariant url = value.as<JsonObject>()["url"];
            if (!url.is<const char *>() || url.as<String>().length() == 0) invalid = "relay.url";
            else if (!parseRelayUrl(url.as<String>(), next)) invalid = "relay.url";
            else {
                restart = true;
            }
        } else if (key == "wifi") {
            if (!value.is<JsonObject>() || value.as<JsonObject>().size() == 0) {
                invalid = "wifi";
                break;
            }
            for (JsonPair part: value.as<JsonObject>()) {
                String field = part.key().c_str();
                JsonVariant selected = part.value();
                if (field == "ssid") {
                    if (!selected.is<const char *>()) invalid = "wifi.ssid";
                    else {
                        String ssid = selected.as<String>();
                        if (ssid.length() == 0 || ssid.length() > 32) invalid = "wifi.ssid";
                        else {
                            wifiSsidSpecified = true;
                            requestedWifiSsid = ssid;
                        }
                    }
                } else if (field == "password") {
                    if (!selected.is<const char *>()) invalid = "wifi.password";
                    else {
                        String password = selected.as<String>();
                        if (password.length() == 0 || password.length() > 63) invalid = "wifi.password";
                        else {
                            password.toCharArray(next.wifiPassword, sizeof(next.wifiPassword));
                        }
                    }
                } else invalid = "wifi";
                if (invalid) break;
            }
            restart = true;
        } else invalid = "data";
        if (invalid) break;
    }

    if (wifiSsidSpecified)
        requestedWifiSsid.toCharArray(next.wifiSsid, sizeof(next.wifiSsid));

    if (invalid) {
        sendSettingsResult(requestId.c_str(), "rejected", invalid);
        return;
    }

    Settings previous = settings;
    settings = next;
    if (!saveSettings()) {
        settings = previous;
        sendSettingsResult(requestId.c_str(), "rejected", "storage");
        return;
    }
    refreshDiode();
    sendSettingsResult(requestId.c_str(), restart ? "restarting" : "applied");
    if (restart) {
        delay(200);
        ESP.restart();
    }
}

void webSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
    if (type == WStype_DISCONNECTED) {
        relayWelcomed = false;
        setDiodeState(DiodeState::ConnectingRelay);
        return;
    }
    if (type == WStype_CONNECTED) {
        relayWelcomed = false;
        sendHello();
        return;
    }
    if (type != WStype_TEXT || length > 2048) return;
    JsonDocument doc;
    if (deserializeJson(doc, payload, length)) return;
    String messageType = doc["type"].as<String>();
    if (messageType == "ping" && relayWelcomed) {
        JsonDocument response;
        response["type"] = "pong";
        response["id"] = String(millis());
        response["replyTo"] = doc["id"].as<String>();
        response["deviceId"] = deviceId();
        response["data"].to<JsonObject>();
        sendJson(response);
    } else if (messageType == "welcome" && doc["deviceId"].as<String>() == deviceId()) {
        relayWelcomed = true;
        setDiodeState(DiodeState::NoSignal);
    } else if (messageType == "atem.state" && relayWelcomed) {
        JsonObject state = doc["data"].as<JsonObject>();
        int program = state["program"].as<int>();
        int preview = state["preview"].as<int>();
        int source = settings.tallyNumber + 1;
        setDiodeState(program == source ? DiodeState::Program :
                       preview == source ? DiodeState::Preview :
                       state["program"].isNull() && state["preview"].isNull()
                           ? DiodeState::NoSignal : DiodeState::Standby);
    } else if (messageType == "settings.set" && relayWelcomed && doc["deviceId"].as<String>() == deviceId()) {
        applySettings(doc);
    }
}

void serviceRelay() {
    startRelay();
    if (relayStarted) {
        webSocket.loop();
    }
}

void stopRelay() {
    webSocket.disconnect();
    relayStarted = false;
    relayWelcomed = false;
}

bool relayConnected() { return webSocket.isConnected() && relayWelcomed; }

