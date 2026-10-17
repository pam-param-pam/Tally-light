const TallyUI = {
    toastTimer: null,

    showToast(message, tone = "default") {
        const toast = document.getElementById("toast");
        if (!toast) return;

        toast.textContent = message;
        toast.dataset.tone = tone;
        toast.classList.add("show");
        window.clearTimeout(this.toastTimer);
        this.toastTimer = window.setTimeout(() => toast.classList.remove("show"), 3500);
    },

    csrfToken() {
        return document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ?? "";
    },

    async request(url, options = {}) {
        const headers = new Headers(options.headers);
        if (options.body) {
            headers.set("Content-Type", "application/json");
            headers.set("X-CSRFToken", this.csrfToken());
        }

        const response = await fetch(url, {cache: "no-store", ...options, headers});
        const body = response.status === 204 ? null : await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(body?.error || body?.detail || "The request failed.");
        }
        return body;
    },
};

window.TallyUI = TallyUI;

document.addEventListener("click", (event) => {
    const closeButton = event.target.closest("[data-close-dialog]");
    if (closeButton) closeButton.closest("dialog")?.close();
});

document.addEventListener("click", (event) => {
    if (!(event.target instanceof HTMLDialogElement)) return;
    const bounds = event.target.getBoundingClientRect();
    const inside = event.clientX >= bounds.left && event.clientX <= bounds.right
        && event.clientY >= bounds.top && event.clientY <= bounds.bottom;
    if (!inside) event.target.close();
});
