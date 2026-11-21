"""Vistas de historial."""

from __future__ import annotations

from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from kp9.history import HistoryEntry
from kp9.tui.views.base import Row, TableView, View
from kp9.tui.widgets import ResponsePanel, last_text, method_text


class HistoryView(TableView):
    COLUMNS = ("FECHA", "ENV", "METHOD", "URL", "STATUS")
    BINDINGS = [Binding("r", "rerun", "re-ejecutar")]

    @property
    def crumb(self) -> str:
        return "historial"

    def heading(self) -> str:
        return "Historial"

    def rows(self) -> list[Row]:
        return [
            Row(
                str(e.id),
                (
                    Text(e.ts.replace("T", " ")[:19]),
                    Text(e.env or "—"),
                    method_text(e.method),
                    Text(e.url),
                    last_text(e),
                ),
                e,
            )
            for e in self.kp9.history.list()
        ]

    def open(self, row: Row) -> None:
        self.kp9.push_view(HistoryDetailView(row.target.id))

    def action_rerun(self) -> None:
        row = self.selected()
        if row is not None:
            self.kp9.rerun(row.target)


class HistoryDetailView(View):
    can_focus = True
    BINDINGS = [Binding("r", "rerun", "re-ejecutar"), Binding("y", "copy_body", "copiar body")]

    def __init__(self, entry_id: int) -> None:
        super().__init__()
        self.entry_id = entry_id
        self.request_text = ""

    def compose(self) -> ComposeResult:
        yield Static(id="request-def")
        yield ResponsePanel(id="response")

    @property
    def panel(self) -> ResponsePanel:
        return self.query_one("#response", ResponsePanel)

    @property
    def crumb(self) -> str:
        return f"#{self.entry_id}"

    @property
    def has_filter(self) -> bool:
        return bool(self.panel.filter_text)

    def apply_filter(self, text: str) -> None:
        self.panel.set_filter(text)

    def entry(self) -> HistoryEntry | None:
        return self.kp9.history.get(self.entry_id)

    def reload(self) -> None:
        entry = self.entry()
        self.border_title = escape(f"Ejecución(#{self.entry_id})")
        if entry is None:
            self.panel.show_error("ejecución no encontrada")
            return
        self.request_text = entry.request_json
        self.query_one("#request-def", Static).update(
            Syntax(entry.request_json, "json", word_wrap=True, background_color="default")
        )
        response = entry.response()
        if response is not None:
            self.panel.show_response(response)
        else:
            self.panel.show_error(entry.error or "sin respuesta")

    def action_rerun(self) -> None:
        entry = self.entry()
        if entry is not None:
            self.kp9.rerun(entry)

    def action_copy_body(self) -> None:
        response = self.panel.current_response
        if response is None:
            self.kp9.notify("no hay respuesta para copiar", severity="warning")
            return
        self.kp9.copy_to_clipboard(response.pretty())
        self.kp9.notify("body copiado")
