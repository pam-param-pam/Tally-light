#include "UsbSetup.h"
#include "SettingsStore.h"
#include "SettingsJson.h"
#include <Arduino.h>
#include <ArduinoJson.h>

namespace {
    char serialLine[2049];
    size_t serialLineLength = 0;
    bool serialLineOverflow = false;
    unsigned long serialLineStartedAt = 0;
}

void sendSerialFrame(JsonDocument &frame) {
    serializeJson(frame, Serial);
    Serial.write('\n');
    Serial.flush();
}

void serialResponse(JsonDocument &frame, const char *type, const char *requestId) {
    static uint32_t responseNumber = 0;
    frame["type"] = type;
    frame["id"] = String(++responseNumber);
    frame["replyTo"] = requestId;
    frame["deviceId"] = deviceId();
}

void serialError(const char *requestId, const char *code) {
    JsonDocument response;
    serialResponse(response, "setup.error", requestId);
    response["data"]["code"] = code;
    sendSerialFrame(response);
}

void serialResult(const char *requestId, const char *state, const char *field = nullptr) {
    JsonDocument response;
    serialResponse(response, "setup.result", requestId);
    response["data"]["state"] = state;
    if (field) response["data"]["field"] = field;
    if (strcmp(state, "saved") == 0) response["data"]["restarting"] = true;
    sendSerialFrame(response);
}

void serialSnapshot(const char *requestId) {
    JsonDocument response;
    serialResponse(response, "setup.snapshot", requestId);
    JsonObject data = response["data"].to<JsonObject>();
    fillSettingsJson(data["settings"].to<JsonObject>(), true);
    data["configured"] = settingsConfigured();
    sendSerialFrame(response);
}

void processSerialLine(char *line) {
    JsonDocument request;
    if (deserializeJson(request, line)) return;
    JsonObject envelope = request.as<JsonObject>();
    const char *requestId = request["id"].as<const char *>();
    if (!requestId || strlen(requestId) == 0 || strlen(requestId) > 64) return;
    if (envelope.isNull() || envelope.size() != 3 || !request["type"].is<const char *>() ||
        !request["data"].is<JsonObject>()) {
        serialError(requestId, "invalid_frame");
        return;
    }
    String type = request["type"].as<String>();
    JsonObject data = request["data"].as<JsonObject>();
    if (type == "setup.get") {
        if (data.size() == 0) serialSnapshot(requestId);
        else serialError(requestId, "invalid_frame");
    } else if (type == "setup.set") {
        Settings next = settings;
        const char *invalid = stageUsbSettings(data, next);
        if (invalid) {
            serialResult(requestId, "rejected", invalid);
            return;
        }
        Settings previous = settings;
        settings = next;
        if (!saveSettings()) {
            settings = previous;
            serialResult(requestId, "rejected", "storage");
            return;
        }
        serialResult(requestId, "saved");
        delay(100);
        ESP.restart();
    } else serialError(requestId, "unsupported_type");
}

void handleSerial() {
    if (serialLineLength && millis() - serialLineStartedAt >= 5000) {
        serialLineLength = 0;
        serialLineOverflow = false;
    }
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') {
            if (!serialLineOverflow && serialLineLength) {
                if (serialLine[serialLineLength - 1] == '\r') --serialLineLength;
                serialLine[serialLineLength] = '\0';
                if (serialLineLength) processSerialLine(serialLine);
            }
            serialLineLength = 0;
            serialLineOverflow = false;
        } else if (!serialLineOverflow) {
            if (serialLineLength == 0) serialLineStartedAt = millis();
            if (serialLineLength < 2048) serialLine[serialLineLength++] = c;
            else serialLineOverflow = true;
        }
    }
}
