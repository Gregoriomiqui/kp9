"""Widgets y helpers compartidos de la TUI."""

from __future__ import annotations

import re

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from kp9.history import HistoryEntry
from kp9.httpclient import Response

METHOD_STYLES = {
    "GET": "bold green",
    "POST": "bold yellow",
    "PUT": "bold blue",
    "PATCH": "bold magenta",
    "DELETE": "bold red",
    "HEAD": "bold cyan",
    "OPTIONS": "bold cyan",
}


def method_text(method: str) -> Text:
    return Text(method, style=METHOD_STYLES.get(method, "bold"))


def status_style(status: int) -> str:
    if status < 300:
        return "bold green"
    if status < 400:
        return "bold cyan"
    if status < 500:
        return "bold yellow"
    return "bold red"


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def last_text(entry: HistoryEntry | None) -> Text:
    if entry is None:
        return Text("—", style="dim")
    if entry.status is None:
        return Text("✗ error", style="bold red")
    return Text(f"{entry.status} · {entry.elapsed_ms or 0:.0f}ms", style=status_style(entry.status))


def mark(name: str, error: str | None) -> Text:
    return Text(f"⚠ {name}", style="bold red") if error else Text(name)


MAX_BODY_CHARS = 200_000
# C0/C1 salvo \t \n \r: evita que una respuesta escriba secuencias de escape en el terminal
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def safe_text(text: str) -> str:
    return _CONTROL.sub("\ufffd", text)


class ResponsePanel(VerticalScroll):
    """Panel de respuesta. Guarda el texto plano mostrado para poder testearlo."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.status_text = ""
        self.headers_text = ""
        self.body_text = ""
        self.error_text = ""
        self.filter_text = ""
        self._response: Response | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="resp-status")
        yield Static(id="resp-headers")
        yield Static(id="resp-body")

    @property
    def current_response(self) -> Response | None:
        return self._response

    def _paint(self, status: Text, headers: str, body: Text | Syntax) -> None:
        self.query_one("#resp-status", Static).update(status)
        self.query_one("#resp-headers", Static).update(Text(headers))
        self.query_one("#resp-body", Static).update(body)

    def show_pending(self) -> None:
        self._response = None
        self.error_text = self.headers_text = self.body_text = ""
        self.status_text = "enviando… (Esc cancela)"
        self._paint(Text(self.status_text, style="bold yellow"), "", Text(""))

    def show_error(self, message: str) -> None:
        self._response = None
        self.error_text = message
        self.status_text = "error"
        self.headers_text = self.body_text = ""
        self._paint(Text(f"✗ {message}", style="bold red"), "", Text(""))

    def show_response(self, response: Response) -> None:
        self._response = response
        self.error_text = ""
        self.status_text = (
            f"{response.status} {response.reason} · {response.elapsed_ms:.0f} ms · "
            f"{human_size(response.size)}"
        )
        self.headers_text = safe_text("\n".join(f"{k}: {v}" for k, v in response.headers))
        self._refresh_body()

    def set_filter(self, text: str) -> None:
        self.filter_text = text.strip()
        self._refresh_body()

    def _refresh_body(self) -> None:
        response = self._response
        if response is None:
            return
        text = safe_text(response.pretty())
        truncated = len(text) > MAX_BODY_CHARS
        if truncated:
            text = text[:MAX_BODY_CHARS]
        if self.filter_text:
            needle = self.filter_text.lower()
            text = "\n".join(line for line in text.splitlines() if needle in line.lower())
        if truncated:
            text += (
                f"\n… respuesta truncada ({human_size(response.size)} en total; "
                "y copia el body completo)"
            )
        self.body_text = text
        body: Text | Syntax
        if response.is_json and not truncated and not self.filter_text:
            body = Syntax(text, "json", word_wrap=True, background_color="default")
        else:
            body = Text(text)
        self._paint(
            Text(self.status_text, style=status_style(response.status)), self.headers_text, body
        )


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("y", "confirm", "sí"),
        Binding("n", "deny", "no"),
        Binding("escape", "deny", "no"),
    ]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(Text(self.question))
            yield Static(Text("y = sí    n / Esc = no", style="bold"))

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)


HELP_ROWS = (
    ("1", "grupos"),
    ("2", "colecciones del grupo actual"),
    ("E", "entornos (Enter activa)"),
    ("h", "historial"),
    (":", "comando: groups · col <nombre> · env <nombre> · history · import <archivo> · q"),
    ("/", "filtrar tabla / buscar en el body"),
    ("Enter", "abrir"),
    ("Esc", "volver / cancelar request en curso / quitar filtro"),
    ("s, Ctrl-R", "enviar request"),
    ("n / e / d", "crear / editar / borrar"),
    ("c", "copiar request como curl"),
    ("y", "copiar body de la respuesta"),
    ("r", "re-ejecutar (historial)"),
    ("?", "esta ayuda"),
)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "cerrar"),
        Binding("question_mark", "close", "cerrar"),
        Binding("q", "close", "cerrar"),
    ]

    def compose(self) -> ComposeResult:
        text = Text()
        for key, description in HELP_ROWS:
            text.append(f"{key:>12}  ", style="bold #ffb000")
            text.append(f"{description}\n")
        with Vertical(id="dialog"):
            yield Static(Text("Atajos de kp9\n", style="bold"))
            yield Static(text)

    def action_close(self) -> None:
        self.dismiss(None)


class NameScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "cancelar")]

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(Text(self.label))
            yield Input(id="name")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
