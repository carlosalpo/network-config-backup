"""Keyboard-first Textual wizard. The UI never persists access credentials."""

from importlib.resources import files
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    ContentSwitcher,
    DataTable,
    Footer,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)

from . import __version__
from .collector import Collection, NetmikoTransport
from .commands import PROFILES, make_jobs, select_commands
from .demo import DemoTransport
from .export import export_collection
from .model import PLATFORMS, Credential, load_inventory, parse_inventory

STEPS = ["Inventory", "Credentials", "Commands", "Check & collect", "Save"]


class BackupApp(App):
    TITLE = "Network Configuration Backup"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+n", "next", "Continue"),
        ("ctrl+b", "back", "Back"),
    ]

    def __init__(self, inventory=None, demo=False):
        super().__init__()
        self.initial_inventory = inventory
        self.demo = demo
        self.devices = []
        self.profiles = {}
        self.assignments = {}
        self.selections = {}
        self.collection = None
        self.step = 0
        self.selected_result = None
        self.running = False
        self.saved_path = None
        self.quit_armed = False

    def compose(self) -> ComposeResult:
        label = (
            "OFFLINE DEMO / SYNTHETIC DATA"
            if self.demo
            else "LIVE SSH / REAL-DEVICE VALIDATION PENDING"
        )
        yield Static(f"NETWORK CONFIGURATION BACKUP   {__version__}\n{label}", id="brand")
        with Horizontal(id="shell"):
            with Vertical(id="steps"):
                for index, name in enumerate(STEPS):
                    yield Static(f"{index + 1}  {name}", id=f"step-{index}")
                yield Static(
                    "Tab / Shift+Tab\nMove focus\n\nSpace\nSelect\n\nCtrl+N\nContinue", id="keys"
                )
            with Vertical(id="workspace"):
                yield Static("Load your devices", id="heading")
                with ContentSwitcher(initial="page-0", id="pages"):
                    with VerticalScroll(id="page-0", classes="page"):
                        yield Label("Inventory file · CSV / YAML / TXT")
                        yield Input(
                            self.initial_inventory or "",
                            placeholder="./devices.csv",
                            id="inventory-path",
                        )
                        yield Label(
                            "Or paste one IP / hostname per line (leave the file path empty)"
                        )
                        yield TextArea(id="hosts")
                        yield Select(
                            [(name, key) for key, name in PLATFORMS.items()],
                            value="cisco_ios",
                            allow_blank=False,
                            id="default-platform",
                        )
                        with Horizontal(classes="actions"):
                            yield Button("Load inventory", id="load", variant="primary")
                            if self.demo:
                                yield Button("Load sample inventory", id="sample")
                        yield DataTable(id="inventory-table", cursor_type="row")
                        yield Static(
                            "No connections are opened until Check & collect. Inventory files contain no passwords.",
                            classes="note",
                        )
                    with VerticalScroll(id="page-1", classes="page"):
                        yield Static(
                            "Assign one profile to all devices, by inventory group, or individually.",
                            classes="note",
                        )
                        yield Select(
                            [
                                ("Same for all devices", "all"),
                                ("By group", "group"),
                                ("Per device", "device"),
                            ],
                            value="group",
                            allow_blank=False,
                            id="credential-mode",
                        )
                        yield Select([], id="credential-scope", prompt="Load inventory first")
                        with Horizontal(classes="columns"):
                            with Vertical(classes="column"):
                                yield Label("Username")
                                yield Input(id="username")
                                yield Label("Authentication method")
                                yield Select(
                                    [("Password", "password"), ("SSH key", "key")],
                                    value="password",
                                    allow_blank=False,
                                    id="method",
                                )
                                yield Label("Password (masked)")
                                yield Input(password=True, id="password")
                                yield Label("Optional enable secret (masked)")
                                yield Input(password=True, id="secret")
                            with Vertical(classes="column"):
                                yield Label("SSH key file · used only with SSH key method")
                                yield Input(placeholder="~/.ssh/id_ed25519", id="key-file")
                                yield Label("Key passphrase (masked)")
                                yield Input(password=True, id="passphrase")
                                yield Label("Verified SSH known_hosts file")
                                yield Input("~/.ssh/known_hosts", id="known-hosts")
                                yield Label("Per-query timeout · 5–120 seconds")
                                yield Input("30", type="integer", id="timeout")
                        yield Button(
                            "Save profile for this session", id="save-profile", variant="primary"
                        )
                        yield Static("", id="credential-status", markup=False)
                        yield Static(
                            "Credentials stay in memory. Unknown or changed SSH keys are rejected. Verify host fingerprints independently before adding them to known_hosts.",
                            classes="note",
                        )
                    with VerticalScroll(id="page-2", classes="page"):
                        yield Select(
                            [], id="command-scope", prompt="Choose a device group / platform"
                        )
                        with Horizontal(classes="columns"):
                            with Vertical(classes="column"):
                                yield Label("Collection profiles")
                                for index, name in enumerate(PROFILES["cisco_ios"]):
                                    yield Checkbox(name, value=index < 3, id=f"profile-{index}")
                            with Vertical(classes="column"):
                                yield Label("Custom queries · one show query per line")
                                yield TextArea(id="custom")
                                yield Static(
                                    "No pipes, redirection, shell commands or configuration changes. Custom queries must fit the supported show families.",
                                    classes="note",
                                )
                        yield Button(
                            "Apply selection to scope", id="apply-commands", variant="primary"
                        )
                        yield DataTable(id="plan-table", cursor_type="row")
                        yield Checkbox(
                            "Discard earlier captures when starting a NEW collection", id="discard"
                        )
                        yield Static(
                            "Check & collect executes the selected queries once. Successful captures remain in memory until exported or the application exits.",
                            classes="note",
                        )
                        yield Button("Check & collect", id="collect", variant="primary")
                    with VerticalScroll(id="page-3", classes="page"):
                        yield Static("", id="counts", markup=False)
                        yield DataTable(id="results-table", cursor_type="row")
                        yield Static(
                            "Select a result to inspect or correct it.",
                            id="result-detail",
                            markup=False,
                        )
                        yield Label("Replacement query · failed results only")
                        yield Input(id="replacement")
                        yield Label("Exclusion reason · required when excluding a query")
                        yield Input(id="reason", max_length=240)
                        with Horizontal(classes="actions"):
                            yield Button("Retry selected", id="retry", variant="primary")
                            yield Button("Exclude with reason", id="exclude")
                            yield Button(
                                "Stop after current query",
                                id="cancel",
                                variant="warning",
                                disabled=True,
                            )
                        yield Static(
                            "Passed captures are retained. Editing and retrying affects only the selected device/query. A timeout closes that device session before further queries.",
                            classes="note",
                        )
                    with VerticalScroll(id="page-4", classes="page"):
                        yield Static("", id="save-summary", markup=False)
                        yield Label("Destination folder · private local export")
                        yield Input("~/Backups/network", id="destination")
                        with Horizontal(classes="columns"):
                            with Vertical(classes="column"):
                                yield Static("Folder preview", classes="subheading")
                                yield Static("", id="folder-preview", markup=False)
                            with Vertical(classes="column"):
                                yield Static("Export contents", classes="subheading")
                                yield Static(
                                    "Original successful outputs\nDevice metadata and UTC timestamps\nHTML summary of every query\nJSON manifest and SHA-256 checksums\nRetry history and exclusion reasons",
                                    id="contents",
                                )
                                yield Static(
                                    "Configurations may contain secrets. Private local files; no automatic Git upload. No restoration is performed.",
                                    classes="note",
                                )
                        yield Checkbox(
                            "I understand that original outputs may contain secrets",
                            id="sensitive-confirm",
                        )
                        yield Button("Save collection", id="export", variant="primary")
                yield Static("Load a device inventory to begin.", id="status", markup=False)
                with Horizontal(id="navigation"):
                    yield Button("Back", id="back")
                    yield Button("Continue", id="next", variant="primary")
        yield Footer()

    def on_resize(self, event):
        self.screen.set_class(event.size.width < 105, "narrow")

    def on_mount(self):
        self.theme = "textual-dark"
        self.query_one("#inventory-table", DataTable).add_columns(
            "Device", "Address", "Platform", "Group", "Site"
        )
        self.query_one("#plan-table", DataTable).add_columns(
            "Device", "Platform", "Queries", "Selection"
        )
        self.query_one("#results-table", DataTable).add_columns(
            "Device", "Query", "Result", "Captured UTC"
        )
        self.show_step(0)
        if self.demo:
            self.load_sample()
        elif self.initial_inventory:
            self.load_devices()

    def value(self, name):
        return self.query_one("#" + name, Input).value.strip()

    def message(self, text):
        self.query_one("#status", Static).update(text)

    def show_step(self, index):
        self.step = index
        self.query_one("#pages", ContentSwitcher).current = f"page-{index}"
        titles = [
            "Load your devices",
            "Connect your devices",
            "Choose what to collect",
            "Review collection results",
            "Save your collection",
        ]
        self.query_one("#heading", Static).update(titles[index])
        for i in range(5):
            self.query_one(f"#step-{i}").set_class(i == index, "active")
        self.query_one("#back", Button).disabled = index == 0
        self.query_one("#next", Button).disabled = index in {2, 4}
        if index == 4:
            self.refresh_save()

    def install_devices(self, devices):
        self.devices = devices
        self.profiles.clear()
        self.assignments.clear()
        self.selections.clear()
        self.collection = None
        self.saved_path = None
        table = self.query_one("#inventory-table", DataTable)
        table.clear()
        for d in devices:
            table.add_row(d.name, d.host, PLATFORMS[d.platform], d.group, d.site)
        scopes = [("All devices", "all")] + [
            (f"{group} / {PLATFORMS[platform]}", f"{group}|{platform}")
            for group, platform in sorted({(d.group, d.platform) for d in devices})
        ]
        scope = self.query_one("#command-scope", Select)
        scope.set_options(scopes)
        scope.value = "all"
        self.credential_scopes()
        self.refresh_plan()
        self.message(f"{len(devices)} devices loaded. No network connections opened.")

    def load_sample(self):
        self.install_devices(
            parse_inventory(files("network_backup").joinpath("data/demo.csv").read_text(), "csv")
        )
        self.query_one("#username", Input).value = "demo-reader"
        self.query_one("#password", Input).value = "demo-only"

    def load_devices(self):
        if self.collection and self.collection.results:
            raise ValueError(
                "Restart the assistant to replace an inventory after collecting; export first."
            )
        path = self.value("inventory-path")
        pasted = self.query_one("#hosts", TextArea).text
        if path and pasted.strip():
            raise ValueError("Choose a file OR pasted hosts; clear the unused input.")
        self.install_devices(
            load_inventory(path)
            if path
            else parse_inventory(pasted, "txt", self.query_one("#default-platform", Select).value)
        )

    def scope_key(self, device):
        mode = self.query_one("#credential-mode", Select).value
        return "all" if mode == "all" else device.group if mode == "group" else device.name

    def credential_scopes(self):
        scopes = sorted({self.scope_key(d) for d in self.devices})
        widget = self.query_one("#credential-scope", Select)
        widget.set_options([(key, key) for key in scopes])
        if scopes:
            widget.value = scopes[0]
        self.refresh_credentials()

    @on(Select.Changed, "#credential-mode")
    def mode_changed(self):
        if self.devices:
            self.profiles.clear()
            self.assignments.clear()
            self.credential_scopes()

    @on(Select.Changed, "#credential-scope")
    def credential_selected(self, event):
        cred = self.profiles.get(str(event.value))
        self.query_one("#username", Input).value = (
            cred.username if cred else ("demo-reader" if self.demo else "")
        )
        self.query_one("#password", Input).value = (
            cred.password if cred else ("demo-only" if self.demo else "")
        )
        self.query_one("#key-file", Input).value = cred.key_file if cred else ""
        self.query_one("#passphrase", Input).value = cred.passphrase if cred else ""
        self.query_one("#secret", Input).value = cred.secret if cred else ""
        self.query_one("#method", Select).value = "key" if cred and cred.key_file else "password"

    def save_profile(self):
        scope = self.query_one("#credential-scope", Select).value
        if scope is Select.NULL:
            raise ValueError("Load an inventory first.")
        key_mode = self.query_one("#method", Select).value == "key"
        cred = Credential(
            self.value("username"),
            "" if key_mode else self.query_one("#password", Input).value,
            self.value("key-file") if key_mode else "",
            self.query_one("#passphrase", Input).value if key_mode else "",
            self.query_one("#secret", Input).value,
        ).validate()
        self.profiles[str(scope)] = cred
        for d in self.devices:
            if self.scope_key(d) == scope:
                self.assignments[d.name] = cred
        self.refresh_credentials()
        self.message("Profile saved in memory for this session only.")

    def refresh_credentials(self):
        names = [d.name for d in self.devices if d.name not in self.assignments]
        self.query_one("#credential-status", Static).update(
            f"{len(self.assignments)} / {len(self.devices)} devices assigned."
            + (" Missing: " + ", ".join(names) if names else " Ready for query selection.")
        )

    def action_next(self):
        if self.running:
            return
        try:
            if self.step == 0:
                if not self.devices:
                    raise ValueError("Load and review your inventory first.")
                self.show_step(1)
            elif self.step == 1:
                if any(d.name not in self.assignments for d in self.devices):
                    raise ValueError("Save a credential profile for every device or group.")
                if not self.demo and not Path(self.value("known-hosts")).expanduser().is_file():
                    raise ValueError("Choose an existing, independently verified known_hosts file.")
                self.show_step(2)
            elif self.step == 3:
                if not self.collection or not any(
                    r.status == "passed" for r in self.collection.results.values()
                ):
                    raise ValueError("Collect at least one successful query before exporting.")
                self.show_step(4)
        except ValueError as exc:
            self.message(str(exc))

    def action_back(self):
        if not self.running and self.step:
            self.show_step(self.step - 1)

    def apply_commands(self):
        scope = self.query_one("#command-scope", Select).value
        if scope is Select.NULL:
            raise ValueError("Choose a query scope.")
        names = [
            name
            for i, name in enumerate(PROFILES["cisco_ios"])
            if self.query_one(f"#profile-{i}", Checkbox).value
        ]
        custom = self.query_one("#custom", TextArea).text
        changes = {}
        for d in self.devices:
            if scope == "all" or scope == f"{d.group}|{d.platform}":
                changes[d.name] = select_commands(d.platform, names, custom)
        self.selections.update(changes)
        self.refresh_plan()
        self.message(f"Queries selected for {len(changes)} devices. Nothing executed yet.")

    def refresh_plan(self):
        table = self.query_one("#plan-table", DataTable)
        table.clear()
        for d in self.devices:
            commands = self.selections.get(d.name, [])
            table.add_row(
                d.name,
                PLATFORMS[d.platform],
                str(len(commands)),
                Text(", ".join(c for c, _ in commands) or "No queries selected"),
            )

    def start_collection(self):
        if not self.devices or any(d.name not in self.assignments for d in self.devices):
            raise ValueError("Load devices and save their access profiles first.")
        jobs = make_jobs(self.devices, self.selections)
        if self.collection and not self.query_one("#discard", Checkbox).value:
            raise ValueError(
                "Export earlier captures first, or explicitly select Discard earlier captures."
            )
        try:
            timeout = int(self.value("timeout"))
        except ValueError:
            raise ValueError("Timeout must be an integer from 5 to 120 seconds.") from None
        transport = (
            DemoTransport() if self.demo else NetmikoTransport(self.value("known-hosts"), timeout)
        )
        self.collection = Collection(jobs, transport)
        self.saved_path = None
        self.selected_result = None
        self.query_one("#discard", Checkbox).value = False
        self.show_step(3)
        self.refresh_results()
        self.set_running(True)
        self.collect_worker()

    def set_running(self, running):
        self.running = running
        for widget in self.query("Button, Input, Select, Checkbox, TextArea"):
            widget.disabled = running
        self.query_one("#cancel", Button).disabled = not running or self.step != 3
        if not running:
            self.query_one("#back", Button).disabled = self.step == 0
            self.query_one("#next", Button).disabled = self.step in {2, 4}

    @work(thread=True, exit_on_error=False)
    def collect_worker(self, keys=None):
        try:
            self.collection.collect(
                dict(self.assignments), keys, lambda: self.call_from_thread(self.refresh_results)
            )
            self.call_from_thread(
                self.message,
                "Collection finished. Review failures or continue to export. Real-device validation remains pending for this release.",
            )
        except Exception:
            self.call_from_thread(
                self.message,
                "Collection stopped unexpectedly. Existing captures remain available; review before retrying.",
            )
        finally:
            self.call_from_thread(self.set_running, False)

    def refresh_results(self):
        table = self.query_one("#results-table", DataTable)
        row = table.cursor_row
        table.clear()
        for key, result in self.collection.results.items():
            table.add_row(
                result.job.device.name,
                Text(result.job.command),
                result.status.upper(),
                result.captured_at or "-",
                key=key,
            )
        if table.row_count:
            table.move_cursor(row=min(row, table.row_count - 1))
        passed = sum(r.status == "passed" for r in self.collection.results.values())
        excluded = sum(r.status == "excluded" for r in self.collection.results.values())
        self.query_one("#counts", Static).update(
            f"{passed} passed   {len(self.collection.results) - passed - excluded} need attention   "
            f"{excluded} excluded   {len(self.collection.results)} queries"
        )

    @on(DataTable.RowHighlighted, "#results-table")
    def result_selected(self, event):
        if not self.collection or event.row_key.value not in self.collection.results:
            return
        self.selected_result = event.row_key.value
        result = self.collection.results[self.selected_result]
        self.query_one("#result-detail", Static).update(
            f"{result.job.device.name} · {result.status.upper()}\n{result.message}"
            + (f"\nExcluded: {result.excluded_reason}" if result.excluded_reason else "")
        )
        self.query_one("#replacement", Input).value = result.job.command

    def retry_selected(self):
        if not self.selected_result:
            raise ValueError("Select a failed query first.")
        result = self.collection.results[self.selected_result]
        if result.status in {"passed", "pending"}:
            raise ValueError("Only failed or excluded results can be retried here.")
        command = self.value("replacement")
        if command != result.job.command or result.status == "excluded":
            self.collection.edit(self.selected_result, command)
        self.saved_path = None
        self.collection.cancel.clear()
        self.set_running(True)
        self.collect_worker([self.selected_result])

    def refresh_save(self):
        passed = sum(r.status == "passed" for r in self.collection.results.values())
        total = len(self.collection.results)
        status = "COMPLETE COLLECTION" if self.collection.complete else "PARTIAL COLLECTION"
        if self.demo:
            status = "SYNTHETIC DEMO / " + status
        self.query_one("#save-summary", Static).update(
            f"{status} · {passed}/{total} queries passed.\n"
            "Unsuccessful and excluded queries remain in the report. This is not a restoration test."
        )
        devices = sorted(
            {
                r.job.device.site + "/" + r.job.device.name
                for r in self.collection.results.values()
                if r.status == "passed"
            }
        )
        self.query_one("#folder-preview", Static).update(
            "backup-<UTC time>-<unique ID>/\n  summary.html\n  manifest.json\n  SHA256SUMS\n  sites/\n"
            + "\n".join("    " + d + "/\n      configuration/ · diagnostics/" for d in devices[:6])
            + ("\n    ..." if len(devices) > 6 else "")
            + "\n\nQuery-to-file mapping: manifest.json"
        )
        self.query_one("#export", Button).label = (
            "Save collection" if self.collection.complete else "Save partial collection"
        )

    @work(thread=True, exit_on_error=False)
    def export_worker(self, destination):
        try:
            path = export_collection(self.collection, destination)
            self.saved_path = path
            self.call_from_thread(self.message, f"Saved privately to {path}. No data uploaded.")
        except (ValueError, OSError) as exc:
            self.call_from_thread(
                self.message,
                str(exc)
                if isinstance(exc, ValueError)
                else "Export failed. Check destination permissions and free space; incomplete private files may remain.",
            )
        finally:
            self.call_from_thread(self.set_running, False)

    @on(Button.Pressed)
    def handle_button(self, event):
        action = event.button.id
        if self.running and action != "cancel":
            return
        try:
            if action == "load":
                self.load_devices()
            elif action == "sample":
                if self.collection:
                    raise ValueError("Restart demo to replace a collected inventory; export first.")
                self.load_sample()
            elif action == "save-profile":
                self.save_profile()
            elif action == "apply-commands":
                self.apply_commands()
            elif action == "collect":
                self.start_collection()
            elif action == "retry":
                self.retry_selected()
            elif action == "exclude":
                if not self.selected_result:
                    raise ValueError("Select a failed query first.")
                self.collection.exclude(self.selected_result, self.value("reason"))
                self.saved_path = None
                self.refresh_results()
            elif action == "cancel":
                self.collection.cancel.set()
                self.message(
                    "Stopping after the current bounded query. Captures already obtained are retained."
                )
            elif action == "export":
                if not self.query_one("#sensitive-confirm", Checkbox).value:
                    raise ValueError(
                        "Confirm that original outputs may contain secrets before exporting."
                    )
                destination = self.value("destination")
                if not destination:
                    raise ValueError("Enter a destination folder.")
                self.set_running(True)
                self.export_worker(destination)
            elif action == "next":
                self.action_next()
            elif action == "back":
                self.action_back()
        except (ValueError, OSError) as exc:
            self.message(
                str(exc)
                if isinstance(exc, ValueError)
                else "Could not read that file; check the path and permissions."
            )

    def action_quit(self):
        if self.running:
            if self.collection:
                self.collection.cancel.set()
            self.message("Stopping safely. Wait for the active operation, then quit again.")
            return
        if self.collection and not self.saved_path and not self.quit_armed:
            self.quit_armed = True
            self.message(
                "Unsaved captures will be lost. Export them, or press Ctrl+Q again to discard and quit."
            )
            return
        self.profiles.clear()
        self.assignments.clear()
        self.exit()
