const liveView = {
    relayStatus: document.getElementById("relay-status"),
    transmitterStatus: document.getElementById("transmitter-status"),
    programSource: document.getElementById("program-source"),
    previewSource: document.getElementById("preview-source"),
    updated: document.getElementById("live-updated"),
    total: document.getElementById("live-total"),
    grid: document.getElementById("live-grid"),
    empty: document.getElementById("live-empty"),
    dialog: document.getElementById("tally-light-dialog"),
    form: document.getElementById("tally-light-form"),
    allBrightness: document.getElementById("all-tally-lights-brightness"),
    allBrightnessValue: document.getElementById("all-tally-lights-brightness-value"),
};

const tallyLightFields = {
    deviceId: document.getElementById("tally-light-device-id"),
    name: document.getElementById("tally-light-name"),
    source: document.getElementById("tally-light-source"),
    brightness: document.getElementById("tally-light-brightness"),
    brightnessValue: document.getElementById("tally-light-brightness-value"),
    relayUrl: document.getElementById("tally-light-relay-url"),
    wifiSsid: document.getElementById("tally-light-wifi-ssid"),
    wifiPassword: document.getElementById("tally-light-wifi-password"),
    toggleWifiPassword: document.getElementById("toggle-wifi-password"),
};

const tallyLights = new Map();
let reconnectTimer;
let leavingPage = false;

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
}

function sourceLabel(source) {
    return source === null || source === undefined ? "—" : `Input ${source}`;
}

function statusLabel(status) {
    return {
        program: "Program",
        preview: "Preview",
        standby: "Standby",
        "no-transmitter": "No transmitter",
    }[status] || "Unknown";
}

function formatTimestamp(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString([], {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
}

function setRelayStatus(connected) {
    liveView.relayStatus.className = `connection-status ${connected ? "connected" : "waiting"}`;
    liveView.relayStatus.lastChild.textContent = connected ? "Live connection active" : "Reconnecting to relay";
}

function renderTallyLight(tallyLight) {
    const safeStatus = ["program", "preview", "standby", "no-transmitter"].includes(tallyLight.status)
        ? tallyLight.status : "no-transmitter";
    return `
    <article class="tally-light-card ${safeStatus}">
      <div class="tally-light-card-heading">
        <span class="tally-light-indicator" aria-hidden="true"></span>
        <div><h3>${escapeHtml(tallyLight.name)}</h3><p>${escapeHtml(tallyLight.deviceId)}</p></div>
        <span class="state-pill">${statusLabel(safeStatus)}</span>
      </div>
      <dl>
        <div><dt>ATEM source</dt><dd>${escapeHtml(tallyLight.source)}</dd></div>
        <div><dt>Brightness</dt><dd>${escapeHtml(tallyLight.settings.brightness)}</dd></div>
      </dl>
      <button class="button secondary edit-tally-light" type="button" data-device-id="${escapeHtml(tallyLight.deviceId)}">Edit Tally Light</button>
    </article>`;
}

function renderSnapshot(snapshot) {
    liveView.transmitterStatus.textContent = snapshot.transmitter_online ? "Connected" : "Not connected";
    liveView.transmitterStatus.className = snapshot.transmitter_online ? "positive-text" : "muted-text";
    liveView.programSource.textContent = sourceLabel(snapshot.program);
    liveView.previewSource.textContent = sourceLabel(snapshot.preview);
    liveView.updated.textContent = formatTimestamp(snapshot.updated_at);

    tallyLights.clear();
    for (const tallyLight of snapshot.tally_lights) tallyLights.set(tallyLight.deviceId, tallyLight);
    liveView.total.textContent = String(snapshot.tally_lights.length);
    liveView.grid.innerHTML = snapshot.tally_lights.map(renderTallyLight).join("");
    liveView.grid.hidden = snapshot.tally_lights.length === 0;
    liveView.empty.hidden = snapshot.tally_lights.length > 0;
    liveView.allBrightness.disabled = snapshot.tally_lights.length === 0;

    if (snapshot.tally_lights.length) {
        const values = new Set(snapshot.tally_lights.map((tallyLight) => tallyLight.settings.brightness));
        if (values.size === 1) {
            const brightness = snapshot.tally_lights[0].settings.brightness;
            liveView.allBrightness.value = brightness;
            liveView.allBrightnessValue.value = brightness;
        } else {
            liveView.allBrightnessValue.value = "Mixed";
        }
    } else {
        liveView.allBrightnessValue.value = "—";
    }
}

function openTallyLightEditor(deviceId) {
    const tallyLight = tallyLights.get(deviceId);
    if (!tallyLight) return;
    const settings = tallyLight.settings;

    document.getElementById("tally-light-dialog-title").textContent = `Edit ${tallyLight.name}`;
    tallyLightFields.deviceId.value = tallyLight.deviceId;
    tallyLightFields.name.value = settings.name;
    tallyLightFields.source.value = settings.source;
    tallyLightFields.brightness.value = settings.brightness;
    tallyLightFields.brightnessValue.value = settings.brightness;
    tallyLightFields.relayUrl.value = settings.relay.url;
    tallyLightFields.wifiSsid.value = settings.wifi.ssid;
    tallyLightFields.wifiPassword.value = settings.wifi.password;
    tallyLightFields.wifiPassword.type = "password";
    tallyLightFields.toggleWifiPassword.textContent = "Show";
    tallyLightFields.toggleWifiPassword.setAttribute("aria-label", "Show Wi-Fi password");
    tallyLightFields.toggleWifiPassword.setAttribute("aria-pressed", "false");
    liveView.dialog.showModal();
}

function createBrightnessScheduler(sendUpdate) {
    let queuedValue;
    let timer;
    let lastSentAt = 0;

    async function flush() {
        timer = undefined;
        if (queuedValue === undefined) return;
        const value = queuedValue;
        queuedValue = undefined;
        lastSentAt = Date.now();
        await sendUpdate(value);
        if (queuedValue !== undefined) schedule(queuedValue);
    }

    function schedule(value) {
        queuedValue = value;
        if (timer !== undefined) return;
        const wait = Math.max(0, 500 - (Date.now() - lastSentAt));
        timer = window.setTimeout(flush, wait);
    }

    return schedule;
}

async function updateAllBrightness(brightness) {
    try {
        await TallyUI.request("/api/tally-lights/settings", {
            method: "PATCH",
            body: JSON.stringify({brightness}),
        });
    } catch (error) {
        TallyUI.showToast(error.message, "error");
    }
}

async function updateTallyLightBrightness(update) {
    try {
        await TallyUI.request(`/api/tally-lights/${encodeURIComponent(update.deviceId)}/settings`, {
            method: "PATCH",
            body: JSON.stringify({brightness: update.brightness}),
        });
    } catch (error) {
        TallyUI.showToast(error.message, "error");
    }
}

const scheduleAllBrightness = createBrightnessScheduler(updateAllBrightness);
const scheduleTallyLightBrightness = createBrightnessScheduler(updateTallyLightBrightness);

function settingsFromForm() {
    return {
        name: tallyLightFields.name.value.trim(),
        source: Number(tallyLightFields.source.value),
        wifi: {
            ssid: tallyLightFields.wifiSsid.value,
            password: tallyLightFields.wifiPassword.value,
        },
    };
}

async function saveTallyLight(event) {
    event.preventDefault();
    const submitButton = liveView.form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
        await TallyUI.request(`/api/tally-lights/${encodeURIComponent(tallyLightFields.deviceId.value)}/settings`, {
            method: "PATCH",
            body: JSON.stringify(settingsFromForm()),
        });
        liveView.dialog.close();
        TallyUI.showToast("Settings sent to the Tally Light.", "success");
    } catch (error) {
        TallyUI.showToast(error.message, "error");
    } finally {
        submitButton.disabled = false;
    }
}

function toggleWifiPassword() {
    const showing = tallyLightFields.wifiPassword.type === "text";
    tallyLightFields.wifiPassword.type = showing ? "password" : "text";
    tallyLightFields.toggleWifiPassword.textContent = showing ? "Show" : "Hide";
    tallyLightFields.toggleWifiPassword.setAttribute("aria-label", `${showing ? "Show" : "Hide"} Wi-Fi password`);
    tallyLightFields.toggleWifiPassword.setAttribute("aria-pressed", String(!showing));
}

function connectLiveSocket() {
    window.clearTimeout(reconnectTimer);
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/dashboard`);

    socket.addEventListener("open", () => setRelayStatus(true));
    socket.addEventListener("message", (event) => {
        const frame = JSON.parse(event.data);
        if (frame.type === "live.state") {
            renderSnapshot(frame.data);
        } else if (frame.type === "ping") {
            const id = globalThis.crypto?.randomUUID?.()
                ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
            socket.send(JSON.stringify({type: "pong", id, replyTo: frame.id, data: {}}));
        }
    });
    socket.addEventListener("close", (event) => {
        setRelayStatus(false);
        if (event.code === 4401) {
            window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
            return;
        }
        if (!leavingPage) reconnectTimer = window.setTimeout(connectLiveSocket, 1000);
    });
    socket.addEventListener("error", () => socket.close());
}

liveView.grid.addEventListener("click", (event) => {
    const button = event.target.closest(".edit-tally-light");
    if (button) openTallyLightEditor(button.dataset.deviceId);
});
liveView.allBrightness.addEventListener("input", () => {
    const brightness = Number(liveView.allBrightness.value);
    liveView.allBrightnessValue.value = brightness;
    scheduleAllBrightness(brightness);
});
tallyLightFields.brightness.addEventListener("input", () => {
    const brightness = Number(tallyLightFields.brightness.value);
    tallyLightFields.brightnessValue.value = brightness;
    scheduleTallyLightBrightness({deviceId: tallyLightFields.deviceId.value, brightness});
});
tallyLightFields.toggleWifiPassword.addEventListener("click", toggleWifiPassword);
liveView.form.addEventListener("submit", saveTallyLight);
window.addEventListener("beforeunload", () => {
    leavingPage = true;
});

connectLiveSocket();
