#pragma once

#include <ArduinoJson.h>

// Build a settings snapshot. The relay token is included only for local USB setup.
void fillSettingsJson(JsonObject saved, bool includeRelayToken);
