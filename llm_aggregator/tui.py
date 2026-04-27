from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Footer, Input, Label,
    Select, Static, TabbedContent, TabPane,
)

from llm_aggregator.key_store import KeyStore

_CONFIG_PATH = Path(__file__).parent / "config" / "providers.json"


def _load_providers() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)["providers"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


CSS = """
Screen {
    overflow: hidden hidden;
    layout: vertical;
}

AppBanner {
    height: 8;
    background: $surface;
    color: $accent;
    text-align: center;
    overflow: hidden hidden;
    padding: 0 1;
}

TabbedContent {
    height: 1fr;
}

DataTable {
    height: 1fr;
}

#add-form {
    padding: 1 2;
    height: auto;
}

.form-row {
    height: 3;
    margin-bottom: 1;
}

.form-label {
    width: 20;
    padding: 1 0;
    color: $text-muted;
}

.form-input {
    width: 1fr;
}

#status-msg {
    height: 1;
    margin: 1 0;
}

Button {
    margin-top: 1;
}

ConfirmScreen {
    align: center middle;
}

ConfirmScreen > Container {
    width: 50;
    height: 9;
    border: round $accent;
    background: $surface;
    padding: 1 2;
}

ConfirmScreen Label {
    margin-bottom: 1;
}

ConfirmScreen Horizontal {
    height: auto;
    align: center middle;
}

ConfirmScreen Button {
    margin: 0 1;
}
"""

BANNER = (
    "██╗     ██╗     ███╗   ███╗    █████╗  ██████╗  ██████╗ ██████╗ ███████╗ ██████╗  █████╗ ████████╗ ██████╗ ██████╗ \n"
    "██║     ██║     ████╗ ████║   ██╔══██╗██╔════╝ ██╔════╝ ██╔══██╗██╔════╝██╔════╝ ██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗\n"
    "██║     ██║     ██╔████╔██║   ███████║██║  ███╗██║  ███╗██████╔╝█████╗  ██║  ███╗███████║   ██║   ██║   ██║██████╔╝\n"
    "██║     ██║     ██║╚██╔╝██║   ██╔══██║██║   ██║██║   ██║██╔══██╗██╔══╝  ██║   ██║██╔══██║   ██║   ██║   ██║██╔══██╗\n"
    "███████╗███████╗██║ ╚═╝ ██║   ██║  ██║╚██████╔╝╚██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║   ██║   ╚██████╔╝██║  ██║\n"
    "╚══════╝╚══════╝╚═╝     ╚═╝   ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝\n"
    "Free-tier API key pool - rotate, cool down, keep going"
)


class AppBanner(Static):
    pass


class ConfirmScreen(ModalScreen[bool]):
    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self._message)
            with Horizontal():
                yield Button("Confirm", variant="error", id="confirm")
                yield Button("Cancel", variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class LLMAggregatorApp(App):
    CSS = CSS
    TITLE = "LLM Aggregator"
    BINDINGS = [
        Binding("d", "deactivate_key", "Deactivate", show=True),
        Binding("c", "clear_cooldown", "Clear Cooldown", show=True),
        Binding("r", "refresh_keys",   "Refresh",       show=True),
        Binding("q", "quit",           "Quit",          show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._store = KeyStore()
        self._providers = _load_providers()

    def compose(self) -> ComposeResult:
        yield AppBanner(BANNER)
        with TabbedContent():
            with TabPane("Keys", id="tab-keys"):
                yield DataTable(id="keys-table", cursor_type="row")
            with TabPane("Add Key", id="tab-add"):
                with Vertical(id="add-form"):
                    with Horizontal(classes="form-row"):
                        yield Label("Provider", classes="form-label")
                        yield Select(
                            [(name, name) for name in sorted(self._providers.keys())],
                            id="inp-provider",
                            classes="form-input",
                            prompt="Select provider...",
                        )
                    with Horizontal(classes="form-row"):
                        yield Label("API Key", classes="form-label")
                        yield Input(
                            placeholder="gsk_...",
                            id="inp-key",
                            classes="form-input",
                            password=True,
                        )
                    with Horizontal(classes="form-row"):
                        yield Label("Category", classes="form-label")
                        yield Select(
                            [("general_purpose", "general_purpose"), ("embedding", "embedding")],
                            id="inp-category",
                            classes="form-input",
                            value="general_purpose",
                        )
                    with Horizontal(classes="form-row"):
                        yield Label("Model (optional)", classes="form-label")
                        yield Input(
                            placeholder="leave blank for provider default",
                            id="inp-model",
                            classes="form-input",
                        )
                    yield Static("", id="status-msg")
                    yield Button("Add Key", variant="success", id="btn-add")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#keys-table", DataTable)
        table.add_columns("ID", "Provider", "Category", "Model", "Active", "Req Today", "Cooldown Until")
        self._load_keys()

    def _load_keys(self) -> None:
        table = self.query_one("#keys-table", DataTable)
        table.clear()
        now = _now_iso()
        for k in self._store.get_all_keys():
            in_cooldown = bool(k["cooldown_until"] and k["cooldown_until"] > now)
            table.add_row(
                str(k["id"]),
                k["provider"],
                k["category"],
                k["model"] or "default",
                "yes" if k["is_active"] else "no",
                str(k["requests_today"]),
                k["cooldown_until"][:19] if in_cooldown else "-",
                key=str(k["id"]),
            )

    def _selected_key_id(self) -> int | None:
        table = self.query_one("#keys-table", DataTable)
        if table.cursor_row < 0 or table.row_count == 0:
            return None
        row = table.get_row_at(table.cursor_row)
        try:
            return int(row[0])
        except (IndexError, ValueError):
            return None

    def action_refresh_keys(self) -> None:
        self._load_keys()

    def action_deactivate_key(self) -> None:
        key_id = self._selected_key_id()
        if key_id is None:
            return
        key = self._store.get_key_by_id(key_id)
        if not key:
            return

        def _handle(confirmed: bool) -> None:
            if confirmed:
                self._store.deactivate_key(key_id)
                self._load_keys()

        self.push_screen(
            ConfirmScreen(f"Deactivate key {key_id} ({key['provider']})?"),
            _handle,
        )

    def action_clear_cooldown(self) -> None:
        key_id = self._selected_key_id()
        if key_id is None:
            return
        key = self._store.get_key_by_id(key_id)
        if not key:
            return
        self._store.clear_cooldown(key_id)
        self._load_keys()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add":
            self._submit_add_key()

    def _submit_add_key(self) -> None:
        status  = self.query_one("#status-msg", Static)
        prov    = self.query_one("#inp-provider", Select)
        key_inp = self.query_one("#inp-key", Input)
        cat     = self.query_one("#inp-category", Select)
        model   = self.query_one("#inp-model", Input)

        provider = str(prov.value) if prov.value and str(prov.value) != "Select.BLANK" else ""
        api_key  = key_inp.value.strip()
        category = str(cat.value) if cat.value else "general_purpose"
        model_v  = model.value.strip() or None

        if not provider:
            status.update("[red]Select a provider[/red]")
            return
        if not api_key:
            status.update("[red]API key required[/red]")
            return

        result = self._store.register_key(
            provider=provider,
            api_key=api_key,
            category=category,
            model=model_v,
            extra_params={},
        )

        if result["success"]:
            status.update(f"[green]✓ {result['message']}[/green]")
            key_inp.value = ""
            model.value   = ""
            self._load_keys()
        else:
            status.update(f"[red]✗ {result['message']}[/red]")


def run() -> None:
    LLMAggregatorApp().run()
