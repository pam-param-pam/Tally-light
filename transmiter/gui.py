"""Tk interface for the Tally Light application backend."""

import queue
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk

from app_backend import AppBackend
from atem_simulator import SimulationSettings
from errors import AppError


class TallyApp:
    def __init__(self, root):
        self.root = root
        self.backend_events = queue.Queue()
        self.backend = AppBackend(on_event=lambda *event: self.backend_events.put(event))
        self.root.title("Tally Lights")
        self.root.geometry("980x760")
        self.root.minsize(780, 620)
        self.job_running = False
        self.tx_running = False
        self.scan_running = False
        self.relay_busy = False
        self.monitor_connected = False
        self.current_page = None
        self._style()
        self._layout()
        self._refresh_navigation()
        self._show_page("settings" if self.backend.profile["setup"] == "unconfigured" else "tally")
        self.root.after(80, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _style(self):
        self.root.configure(bg="#f3f6fb")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f6fb")
        style.configure("TLabel", background="#f3f6fb", foreground="#26344a", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#f3f6fb", foreground="#203552", font=("Segoe UI Semibold", 15))
        style.configure("Hint.TLabel", background="#f3f6fb", foreground="#68788e", font=("Segoe UI", 9))
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#2864dc", foreground="white")
        style.map("Accent.TButton", background=[("active", "#1b54c4")])
        style.configure("TEntry", padding=5)
        style.configure("Treeview", rowheight=27)

    def _layout(self):
        header = tk.Frame(self.root, bg="#203552", height=76)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Tally Lights", bg="#203552", fg="white",
                 font=("Segoe UI Semibold", 20)).pack(anchor="w", padx=24, pady=(12, 0))
        tk.Label(header, text="Configure Tally Lights over USB · send ATEM cues through your relay",
                 bg="#203552", fg="#c7d5ee", font=("Segoe UI", 10)).pack(anchor="w", padx=25)

        nav = ttk.Frame(self.root, padding=(18, 14, 18, 0))
        nav.pack(fill="x")
        self.nav = {}
        for key, title in (("settings", "Settings"), ("tally", "Configure a Tally Light"),
                           ("transmit", "Run transmitter"), ("monitor", "Serial monitor")):
            button = ttk.Button(nav, text=title, command=lambda page=key: self._show_page(page))
            button.pack(side="left", padx=(0, 8))
            self.nav[key] = button

        viewport = ttk.Frame(self.root)
        viewport.pack(fill="both", expand=True)
        viewport.rowconfigure(0, weight=1)
        viewport.columnconfigure(0, weight=1)
        self.page_canvas = tk.Canvas(viewport, bg="#f3f6fb", highlightthickness=0,
                                     yscrollincrement=24, xscrollincrement=24)
        self.page_canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(viewport, orient="vertical", command=self.page_canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(viewport, orient="horizontal", command=self.page_canvas.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.page_canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.host = ttk.Frame(self.page_canvas, padding=18)
        self.page_window = self.page_canvas.create_window((0, 0), window=self.host, anchor="nw")
        self.host.bind("<Configure>", self._resize_page)
        self.page_canvas.bind("<Configure>", self._resize_page)
        self.root.bind("<MouseWheel>", self._scroll_page, add="+")
        self.root.bind("<Button-4>", self._scroll_page, add="+")
        self.root.bind("<Button-5>", self._scroll_page, add="+")
        self.pages = {key: ttk.Frame(self.host) for key in self.nav}
        self._settings_page()
        self._tally_page()
        self._transmit_page()
        self._monitor_page()

    def _resize_page(self, _event=None):
        width = max(self.host.winfo_reqwidth(), self.page_canvas.winfo_width())
        height = max(self.host.winfo_reqheight(), self.page_canvas.winfo_height())
        self.page_canvas.itemconfigure(self.page_window, width=width, height=height)
        self.page_canvas.configure(scrollregion=(0, 0, width, height))

    def _scroll_page(self, event):
        # Text logs, lists and dropdowns keep their own wheel behavior.
        widget = event.widget
        if widget.winfo_class() in ("Text", "Treeview", "Listbox", "TCombobox", "TSpinbox"):
            return
        if not (widget == self.page_canvas or str(widget).startswith(str(self.host) + ".")
                or widget == self.host):
            return
        if getattr(event, "num", None) in (4, 5):
            steps = -1 if event.num == 4 else 1
        elif event.delta:
            steps = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        else:
            return
        self.page_canvas.yview_scroll(steps, "units")
        return "break"

    def _section(self, parent, title, hint=""):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 16))
        ttk.Label(frame, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, 3))
        if hint:
            ttk.Label(frame, text=hint, style="Hint.TLabel").pack(anchor="w", pady=(0, 8))
        return frame

    def _field(self, parent, row, label, variable, *, password=False, width=40):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=5)
        entry = ttk.Entry(parent, textvariable=variable, width=width, show="•" if password else "")
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        parent.columnconfigure(1, weight=1)
        if password:
            button = ttk.Button(parent, text="Show", width=6)

            def toggle():
                visible = bool(entry.cget("show"))
                entry.configure(show="" if visible else "•")
                button.configure(text="Hide" if visible else "Show")

            button.configure(command=toggle)
            button.grid(row=row, column=2, padx=(8, 0))
        return entry

    def _settings_page(self):
        page = self.pages["settings"]
        section = self._section(page, "Relay server", "Import the connection profile downloaded from the relay dashboard.")
        fields = ttk.Frame(section)
        fields.pack(fill="x")
        self.credential_file = tk.StringVar()
        credential_entry = self._field(fields, 0, "Connection profile", self.credential_file)
        credential_entry.configure(state="readonly")
        ttk.Button(fields, text="Browse…", command=self._choose_credentials).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(section, text="The file contains separate transmitter and Tally Light tokens. It is verified before being saved.",
                  style="Hint.TLabel", wraplength=760).pack(anchor="w", pady=(5, 0))
        self.connection_profile_status = tk.StringVar()
        ttk.Label(section, textvariable=self.connection_profile_status, style="Hint.TLabel").pack(
            anchor="w", pady=(8, 0))
        self._refresh_connection_profile_status()
        actions = ttk.Frame(section)
        actions.pack(anchor="w", pady=(17, 0))
        self.relay_save_button = ttk.Button(actions, text="Import and verify", style="Accent.TButton",
                                            command=self._import_profile)
        self.relay_save_button.pack(side="left", padx=(0, 8))
        self.relay_status = tk.StringVar(value=self.backend.storage_error or "")
        ttk.Label(section, textvariable=self.relay_status, style="Hint.TLabel").pack(anchor="w", pady=(13, 0))

        wifi = self._section(
            page, "Default Tally Light Wi-Fi",
            "Save Wi-Fi details that can be copied into any connected Tally Light.")
        wifi_fields = ttk.Frame(wifi)
        wifi_fields.pack(fill="x")
        self.default_wifi_ssid = tk.StringVar(value=self.backend.profile["default_wifi_ssid"])
        self.default_wifi_password = tk.StringVar(value=self.backend.profile["default_wifi_password"])
        self._field(wifi_fields, 0, "Wi-Fi name", self.default_wifi_ssid)
        self._field(wifi_fields, 1, "Wi-Fi password", self.default_wifi_password, password=True)
        ttk.Button(wifi, text="Save default Wi-Fi", command=self._save_default_wifi).pack(
            anchor="w", pady=(12, 0))
        self.default_wifi_status = tk.StringVar()
        ttk.Label(wifi, textvariable=self.default_wifi_status, style="Hint.TLabel").pack(
            anchor="w", pady=(8, 0))

        storage = self._section(page, "Saved application data", "Clear preferences and return to first setup.")
        ttk.Label(storage, text=str(self.backend.store.folder), style="Hint.TLabel",
                  wraplength=760).pack(anchor="w")
        self.relay_clear_button = ttk.Button(storage, text="Clear all saved data", command=self._clear_all)
        self.relay_clear_button.pack(anchor="w", pady=(12, 0))

    def _save_default_wifi(self):
        try:
            self.backend.save_default_wifi(
                self.default_wifi_ssid.get(), self.default_wifi_password.get())
        except (AppError, OSError) as exc:
            self.default_wifi_status.set(str(exc))
            return
        self.default_wifi_ssid.set(self.backend.profile["default_wifi_ssid"])
        self.default_wifi_status.set("Default Wi-Fi saved.")
        self._refresh_default_wifi_button()

    def _import_profile(self):
        if self.relay_busy:
            return
        filename = self.credential_file.get()
        self.relay_busy = True
        for button in (self.relay_save_button, self.relay_clear_button):
            button.state(["disabled"])
        self.relay_status.set("Importing the connection profile and testing the relay…")

        try:
            self.backend.import_profile(filename)
        except AppError as exc:
            self.backend_events.put(("relay_done", str(exc)))

    def _choose_credentials(self):
        filename = filedialog.askopenfilename(
            title="Import connection profile",
            filetypes=(("Tally Light connection profile", "*.json"), ("All files", "*.*")),
        )
        if filename:
            self.credential_file.set(filename)

    def _clear_all(self):
        if not messagebox.askyesno("Clear saved data", "Delete all saved Tally Lights application data and return to setup?"):
            return
        try:
            self.backend.clear_all()
        except (AppError, OSError) as exc:
            self.relay_status.set(str(exc))
            return
        self.credential_file.set("")
        self.default_wifi_ssid.set("")
        self.default_wifi_password.set("")
        self.default_wifi_status.set("")
        self._refresh_default_wifi_button()
        self._refresh_connection_profile_status()
        self.relay_status.set("Saved application data cleared.")
        self._refresh_navigation()
        self._show_page("settings")

    def _tally_page(self):
        page = self.pages["tally"]
        controls = ttk.Frame(page)
        controls.pack(side="bottom", fill="x", pady=(12, 0))
        self.save_button = ttk.Button(controls, text="Save to Tally Light", style="Accent.TButton", command=self._save_tally)
        self.tally_status = tk.StringVar(value="Select the Tally Light's USB port, then connect.")
        self.tally_status_label = ttk.Label(
            controls, textvariable=self.tally_status, style="Hint.TLabel")
        self.tally_status_label.pack(side="left", padx=13)
        self.backend.disconnect_tally()

        canvas = tk.Canvas(page, bg="#f3f6fb", highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(canvas, padding=(0, 0, 10, 0))
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        self.tally_canvas = canvas

        usb = self._section(content, "USB connection", "Connect to load and edit this Tally Light's settings.")
        row = ttk.Frame(usb)
        row.pack(fill="x")
        self.port = tk.StringVar()
        self.port_box = ttk.Combobox(row, textvariable=self.port, state="readonly", width=34)
        self.port_box.pack(side="left", fill="x", expand=True)
        self.port_box.bind("<<ComboboxSelected>>", self._selected_tally_port_changed)
        self.refresh_ports_button = ttk.Button(row, text="Refresh ports", command=self._refresh_ports)
        self.refresh_ports_button.pack(side="left", padx=8)
        self.connect_tally_button = ttk.Button(
            row, text="Connect to Tally Light", command=self._connect_tally_light)
        self.connect_tally_button.pack(side="left")
        self.device_info = tk.StringVar(value="No Tally Light connected")
        ttk.Label(usb, textvariable=self.device_info, style="Hint.TLabel").pack(anchor="w", pady=(7, 0))

        self.tally_settings = self._section(
            content, "Tally Light settings", "Every Tally Light connects through the relay server.")
        fields = ttk.Frame(self.tally_settings)
        fields.pack(fill="x")
        self.name = tk.StringVar()
        self.source = tk.StringVar()
        self.brightness = tk.StringVar()
        self.wifi_ssid = tk.StringVar()
        self.wifi_password = tk.StringVar()
        self._field(fields, 0, "Tally Light name", self.name)
        self._field(fields, 1, "Source number", self.source)
        self._field(fields, 2, "Brightness (0–255)", self.brightness)
        self._field(fields, 3, "Wi-Fi name", self.wifi_ssid)
        self._field(fields, 4, "Wi-Fi password", self.wifi_password, password=True)
        self.default_wifi_button = ttk.Button(
            fields, text="Use default Wi-Fi", command=self._use_default_wifi)
        self.default_wifi_button.grid(row=5, column=1, sticky="w", pady=(8, 0))
        self._refresh_default_wifi_button()

        self.relay_info = ttk.Label(self.tally_settings, style="Hint.TLabel", wraplength=700)
        self.relay_info.pack(anchor="w", pady=(10, 0))
        self.tally_settings.pack_forget()
        self._refresh_ports()
        self._bind_scroll(content)

    def _bind_scroll(self, widget):
        widget.bind("<MouseWheel>", self._scroll_tally, add="+")
        widget.bind("<Button-4>", self._scroll_tally, add="+")
        widget.bind("<Button-5>", self._scroll_tally, add="+")
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def _scroll_tally(self, event):
        if self.current_page != "tally":
            return
        units = (-1 if event.num == 4 else 1) if getattr(event, "num", None) in (4, 5) else -int(event.delta / 120)
        self.tally_canvas.yview_scroll(units, "units")
        return "break"

    def _selected_tally_port_changed(self, _event=None):
        self._hide_tally_settings()
        self.tally_status.set("Connect to load this Tally Light's settings.")

    def _hide_tally_settings(self):
        self.backend.disconnect_tally()
        self.tally_settings.pack_forget()
        self.save_button.pack_forget()
        self.device_info.set("No Tally Light connected")

    def _refresh_ports(self):
        self._hide_tally_settings()
        try:
            names = [device for device, _description in self.backend.ports()]
        except Exception as exc:
            self.tally_status.set(str(exc))
            return
        self.port_box["values"] = names
        if names and self.port.get() not in names:
            self.port.set(names[0])
        elif not names:
            self.port.set("")

    def _tally_form(self):
        return {"name": self.name.get(), "source": self.source.get(), "brightness": self.brightness.get(),
                "wifi_ssid": self.wifi_ssid.get(), "wifi_password": self.wifi_password.get()}

    def _use_default_wifi(self):
        try:
            ssid, password = self.backend.default_wifi()
        except AppError as exc:
            self.tally_status.set(str(exc))
            return
        self.wifi_ssid.set(ssid)
        self.wifi_password.set(password)
        self.tally_status.set("Default Wi-Fi applied. Save to update the Tally Light.")

    def _refresh_default_wifi_button(self):
        self.default_wifi_button.state(
            ["!disabled"] if self.backend.default_wifi_configured else ["disabled"])

    def _run_usb(self, operation, message, form=None):
        try:
            self.backend.start_usb(operation, self.port.get().strip(), form)
        except AppError as exc:
            self.tally_status.set(str(exc))
            return
        self.job_running = True
        self.save_button.state(["disabled"])
        self.connect_tally_button.state(["disabled"])
        self.port_box.configure(state="disabled")
        self.refresh_ports_button.state(["disabled"])
        self.tally_status.set(message)

    def _connect_tally_light(self):
        self._hide_tally_settings()
        self._run_usb("connect", "Connecting to Tally Light…")

    def _save_tally(self):
        self._run_usb("save", "Saving Tally Light settings…", self._tally_form())

    def _show_snapshot(self, frame, status="Tally Light connected. Settings loaded."):
        saved = frame["data"]["settings"]
        wifi = saved["wifi"]
        self.device_info.set(f"{frame['deviceId']} · {'configured' if frame['data']['configured'] else 'needs setup'}")
        self.name.set(saved["name"])
        self.source.set(str(saved["source"]))
        self.brightness.set(str(saved["brightness"]))
        self.wifi_ssid.set(wifi["ssid"])
        self.wifi_password.set(wifi["password"])
        self.tally_settings.pack(fill="x", pady=(0, 16))
        self.save_button.pack(side="left", before=self.tally_status_label)
        self.tally_status.set(status)

    def _monitor_page(self):
        page = self.pages["monitor"]
        connection = self._section(
            page, "Serial monitor",
            "Configured for the Tally Light firmware: 115200 baud · 8 data bits · no parity · 1 stop bit · no flow control.")
        row = ttk.Frame(connection)
        row.pack(fill="x")
        self.monitor_port = tk.StringVar()
        self.monitor_port_box = ttk.Combobox(row, textvariable=self.monitor_port, state="readonly", width=34)
        self.monitor_port_box.pack(side="left", fill="x", expand=True)
        self.monitor_refresh_button = ttk.Button(row, text="Refresh ports", command=self._refresh_monitor_ports)
        self.monitor_refresh_button.pack(side="left", padx=8)
        self.monitor_connect_button = ttk.Button(
            row, text="Connect", style="Accent.TButton", command=self._toggle_monitor)
        self.monitor_connect_button.pack(side="left")
        self.monitor_status = tk.StringVar(value="Not connected")
        ttk.Label(connection, textvariable=self.monitor_status, style="Hint.TLabel").pack(
            anchor="w", pady=(7, 0))

        output_section = ttk.Frame(page)
        output_section.pack(fill="both", expand=True)
        output_header = ttk.Frame(output_section)
        output_header.pack(fill="x", pady=(0, 7))
        ttk.Label(output_header, text="Output", style="Title.TLabel").pack(side="left")
        ttk.Button(output_header, text="Clear", command=self._clear_monitor).pack(side="right")
        self.monitor_output = scrolledtext.ScrolledText(
            output_section, state="disabled", wrap="word", font=("Consolas", 9),
            bg="#101828", fg="#d0d5dd", insertbackground="white")
        self.monitor_output.pack(fill="both", expand=True)

        send_row = ttk.Frame(page)
        send_row.pack(fill="x", pady=(10, 0))
        self.monitor_input = tk.StringVar()
        self.monitor_input_entry = ttk.Entry(send_row, textvariable=self.monitor_input)
        self.monitor_input_entry.pack(side="left", fill="x", expand=True)
        self.monitor_input_entry.bind("<Return>", self._send_monitor_line)
        self.monitor_send_button = ttk.Button(send_row, text="Send line", command=self._send_monitor_line)
        self.monitor_send_button.pack(side="left", padx=(8, 0))
        self.monitor_send_button.state(["disabled"])
        self._refresh_monitor_ports()

    def _refresh_monitor_ports(self):
        try:
            names = [device for device, _description in self.backend.ports()]
        except Exception as exc:
            self.monitor_status.set(str(exc))
            return
        self.monitor_port_box["values"] = names
        if names and self.monitor_port.get() not in names:
            self.monitor_port.set(names[0])
        elif not names:
            self.monitor_port.set("")

    def _toggle_monitor(self):
        if self.monitor_connected:
            self.monitor_status.set("Disconnecting…")
            self.backend.disconnect_monitor()
            return
        port = self.monitor_port.get().strip()
        try:
            self.backend.connect_monitor(port)
        except AppError as exc:
            self.monitor_status.set(str(exc))
            return
        self.monitor_connected = True
        self.monitor_port_box.configure(state="disabled")
        self.monitor_refresh_button.state(["disabled"])
        self.monitor_connect_button.configure(text="Disconnect")
        self.monitor_send_button.state(["!disabled"])
        self.monitor_status.set(f"Connected to {port}")
        self._hide_tally_settings()
        self.connect_tally_button.state(["disabled"])
        self.save_button.state(["disabled"])

    def _send_monitor_line(self, _event=None):
        text = self.monitor_input.get()
        if not text:
            return
        try:
            self.backend.send_monitor_line(text)
        except AppError as exc:
            self.monitor_status.set(str(exc))
            return
        self._append_monitor(f"→ {text}\n")
        self.monitor_input.set("")

    def _append_monitor(self, text):
        self.monitor_output.configure(state="normal")
        self.monitor_output.insert("end", text)
        lines = int(self.monitor_output.index("end-1c").split(".")[0])
        if lines > 5000:
            self.monitor_output.delete("1.0", f"{lines - 5000}.0")
        self.monitor_output.see("end")
        self.monitor_output.configure(state="disabled")

    def _clear_monitor(self):
        self.monitor_output.configure(state="normal")
        self.monitor_output.delete("1.0", "end")
        self.monitor_output.configure(state="disabled")

    def _transmit_page(self):
        page = self.pages["transmit"]
        summary = self._section(page, "Transmitter", "Connection details come from Settings.")
        self.transmit_relay = tk.StringVar()
        ttk.Label(summary, textvariable=self.transmit_relay, style="Hint.TLabel").pack(anchor="w")
        self.atem_options = ttk.Frame(summary)
        self.atem_options.pack(fill="x", pady=(12, 0))
        self.tx_atem_ip = tk.StringVar(value=self.backend.profile["last_atem_ip"])
        self._field(self.atem_options, 0, "ATEM IP address", self.tx_atem_ip)
        scan_row = ttk.Frame(self.atem_options)
        scan_row.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        self.scan_scope = tk.StringVar(value=self.backend.scan_ranges())
        ttk.Entry(scan_row, textvariable=self.scan_scope).pack(side="left", fill="x", expand=True)
        self.scan_button = ttk.Button(scan_row, text="Scan networks", command=self._toggle_scan)
        self.scan_button.pack(side="left", padx=(8, 0))
        self.scan_status = tk.StringVar(value="Enter IPv4 CIDRs separated by commas. A running local simulator is included automatically.")
        ttk.Label(self.atem_options, textvariable=self.scan_status, style="Hint.TLabel").grid(
            row=2, column=1, sticky="w", pady=(6, 0))
        self.results = ttk.Treeview(self.atem_options, columns=("ip", "model"), show="headings", height=4)
        self.results.heading("ip", text="IP address")
        self.results.heading("model", text="Model")
        self.results.column("ip", width=160)
        self.results.column("model", width=300)
        self.results.grid(row=3, column=1, sticky="ew", pady=(8, 0))
        self.results.bind("<<TreeviewSelect>>", self._choose_switcher)

        simulator = ttk.LabelFrame(summary, text="Simulated ATEM (pyAtemSim)", padding=10)
        simulator.pack(fill="x", pady=(12, 0))
        self.sim_button = ttk.Button(simulator, text="Start simulator", command=self._toggle_simulator)
        self.sim_button.grid(row=0, column=0, padx=(0, 10))
        self.sim_status = tk.StringVar(value="Local ATEM at 127.0.0.1 · inputs 1–8")
        ttk.Label(simulator, textvariable=self.sim_status).grid(row=0, column=1, columnspan=3, sticky="w")
        self.sim_first = tk.StringVar(value="1")
        self.sim_last = tk.StringVar(value="3")
        self.sim_duration = tk.StringVar(value="2000")
        fields = (("First source", self.sim_first), ("Last source", self.sim_last),
                  ("Duration per change (ms)", self.sim_duration))
        for column, (label, variable) in enumerate(fields):
            ttk.Label(simulator, text=label).grid(row=1, column=column, sticky="w", pady=(10, 0))
            ttk.Entry(simulator, textvariable=variable, width=12).grid(
                row=2, column=column, sticky="w", padx=(0, 12))
        self.sim_apply = ttk.Button(simulator, text="Apply settings", command=self._apply_simulator)
        self.sim_apply.grid(row=2, column=4, padx=10)
        self.sim_apply.state(["disabled"])
        ttk.Label(simulator, text="Hold each Program/Preview pair, then switch directly to the next. 2000 ms = 2 seconds.",
                  style="Hint.TLabel").grid(row=3, column=0, columnspan=5, sticky="w", pady=(8, 0))
        actions = ttk.Frame(summary)
        actions.pack(anchor="w", pady=(14, 0))
        self.tx_button = ttk.Button(actions, text="Start transmitter", style="Accent.TButton",
                                    command=self._toggle_transmitter)
        self.tx_button.pack(side="left")
        self.tx_status = tk.StringVar(value="Not transmitting")
        ttk.Label(actions, textvariable=self.tx_status, style="Hint.TLabel").pack(side="left", padx=13)
        self.tx_state = tk.StringVar(value="Program —     Preview —")
        ttk.Label(summary, textvariable=self.tx_state, style="Title.TLabel").pack(anchor="w", pady=(12, 0))

        logs = self._section(page, "Transmitter log")
        self.log_text = scrolledtext.ScrolledText(logs, height=11, state="disabled", wrap="word",
                                                 font=("Consolas", 9), bg="#fff", fg="#26344a")
        self.log_text.pack(fill="both", expand=True)

    def _toggle_simulator(self):
        if self.backend.simulator.running:
            self.backend.simulator.stop()
            return
        try:
            self.backend.simulator.start(self._simulator_settings())
        except AppError as exc:
            self.sim_status.set(str(exc))
            return
        self.tx_atem_ip.set(self.backend.simulator.address)
        self.sim_button.configure(text="Stop simulator")
        self.sim_apply.state(["!disabled"])

    def _simulator_settings(self):
        return SimulationSettings.from_values(self.sim_first.get(), self.sim_last.get(),
                                              self.sim_duration.get())

    def _apply_simulator(self):
        try:
            self.backend.simulator.configure(self._simulator_settings())
        except AppError as exc:
            self.sim_status.set(str(exc))

    def _toggle_scan(self):
        if self.scan_running:
            self.backend.stop_scan()
            return
        try:
            self.backend.start_scan(self.scan_scope.get())
        except AppError as exc:
            self.scan_status.set(str(exc))
            return
        self.scan_running = True
        self.scan_button.configure(text="Cancel scan")
        self.results.delete(*self.results.get_children())
        self.scan_status.set("Scanning…")

    def _choose_switcher(self, _event):
        selection = self.results.selection()
        if selection:
            self.tx_atem_ip.set(self.results.item(selection[0], "values")[0])

    def _toggle_transmitter(self):
        if self.tx_running:
            self.backend.stop_transmitter()
            self.tx_status.set("Stopping…")
            return
        try:
            self.backend.start_transmitter(self.tx_atem_ip.get())
        except (AppError, ValueError, OSError) as exc:
            self.tx_status.set(str(exc))
            return
        self.tx_running = True
        self.tx_button.configure(text="Stop transmitter")

    def _refresh_navigation(self):
        self.nav["tally"].state(["!disabled"] if self.backend.relay_enabled else ["disabled"])
        self.nav["transmit"].state(["!disabled"] if self.backend.relay_enabled else ["disabled"])
        self.transmit_relay.set(
            self.backend.profile['relay_url']
            if self.backend.relay_enabled
                                else "Relay setup is required to transmit.")
        self.relay_info.configure(
            text=f"Using saved relay: {self.backend.profile['relay_url']}"
            if self.backend.relay_enabled else "Import a connection profile first.")

    def _refresh_connection_profile_status(self):
        self.connection_profile_status.set(
            f"Connection profile loaded · {self.backend.profile['relay_url']}"
            if self.backend.relay_enabled else "No connection profile loaded.")

    def _show_page(self, name):
        if name == "tally" and self.backend.profile["setup"] == "unconfigured":
            name = "settings"
        if name == "transmit" and not self.backend.relay_enabled:
            name = "settings"
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        self.current_page = name
        self.root.update_idletasks()
        self._resize_page()
        self.page_canvas.yview_moveto(0)
        self.page_canvas.xview_moveto(0)

    def _append_log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{datetime.now():%H:%M:%S}  {text}\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 500:
            self.log_text.delete("1.0", f"{lines - 500}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_events(self):
        try:
            while True:
                kind, *values = self.backend_events.get_nowait()
                if kind == "relay_done":
                    self.relay_busy = False
                    for button in (self.relay_save_button, self.relay_clear_button):
                        button.state(["!disabled"])
                    if values[0]:
                        self.relay_status.set(values[0])
                    else:
                        self.credential_file.set("")
                        self.relay_status.set("Connection profile verified. Settings saved.")
                        self._refresh_navigation()
                        self._refresh_connection_profile_status()
                        self._show_page("tally")
                elif kind == "usb_done":
                    operation, result, error = values
                    self.job_running = False
                    self.port_box.configure(state="readonly")
                    self.refresh_ports_button.state(["!disabled"])
                    self.save_button.state(["!disabled"])
                    self.connect_tally_button.state(["!disabled"])
                    if error:
                        self._hide_tally_settings()
                        self.tally_status.set(error)
                    elif operation == "connect":
                        self._show_snapshot(result)
                    else:
                        self._show_snapshot(result, "Settings saved and verified after restart.")
                elif kind == "found":
                    found = values[0]
                    self.results.insert("", "end", values=(found.ip, found.model))
                elif kind == "scan_progress":
                    self.scan_status.set(f"Checked {values[0]} of {values[1]} addresses")
                elif kind == "scan_done":
                    self.scan_running = False
                    self.scan_button.configure(text="Scan networks")
                    self.scan_status.set(values[0])
                elif kind == "tx_status":
                    self.tx_status.set(values[0])
                elif kind == "tx_state":
                    self.tx_state.set(f"Program {values[0] or '—'}     Preview {values[1] or '—'}")
                elif kind == "tx_done":
                    self.tx_running = False
                    self.tx_button.configure(text="Start transmitter")
                elif kind == "sim_status":
                    self.sim_status.set(values[0])
                    running = self.backend.simulator.running
                    self.sim_button.configure(text="Stop simulator" if running else "Start simulator")
                    self.sim_apply.state(["!disabled"] if running else ["disabled"])
                elif kind == "monitor_data":
                    self._append_monitor(values[0])
                elif kind == "monitor_closed":
                    self.monitor_connected = False
                    self.monitor_port_box.configure(state="readonly")
                    self.monitor_refresh_button.state(["!disabled"])
                    self.monitor_connect_button.configure(text="Connect")
                    self.monitor_send_button.state(["disabled"])
                    if not self.job_running:
                        self.connect_tally_button.state(["!disabled"])
                        self.save_button.state(["!disabled"])
                    self.monitor_status.set(
                        f"Serial connection closed: {values[0]}" if values[0] else "Not connected")
                elif kind == "log":
                    self._append_log(values[0])
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def _close(self):
        self.backend.close()
        self.root.destroy()


def main():
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            ctypes.windll.user32.ShowWindow(console, 0)
    root = tk.Tk()
    TallyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
