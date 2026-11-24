"""Editor integrado de requests, con autocompletado de `{{variables}}`."""

from __future__ import annotations

from pathlib import Path
from typing import get_args

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Select, Static

from kp9.form import FormError, body_to_text, build_request, pairs_to_text
from kp9.model import BodyType, HttpMethod, Request
from kp9.store import write_json
from kp9.tui.completion import VariablesProvider, VarInput, VarSuggestions, VarTextArea
from kp9.tui.widgets import ConfirmScreen

METHODS: tuple[str, ...] = get_args(HttpMethod)
BODY_TYPES: tuple[str, ...] = get_args(BodyType)
HINT = "ctrl+s guardar · esc cancelar · tab siguiente campo · {{ sugiere variables (↑↓ elegir, tab/enter insertar)"


class RequestEditorScreen(ModalScreen[bool]):
    """Edita método, URL, params, headers y body. Devuelve True si guardó."""

    BINDINGS = [
        Binding("ctrl+s", "save", "guardar", priority=True),
        Binding("escape", "cancel", "cancelar"),
    ]

    def __init__(self, request_path: Path, request: Request, variables: VariablesProvider) -> None:
        super().__init__()
        self.request_path = request_path
        self.original = request
        self._variables = variables
        self.error_text = ""
        self._initial: tuple[str, ...] = ()

    def compose(self) -> ComposeResult:
        req = self.original
        with Vertical(id="editor"):
            yield Static(Text(f"Editar: {req.name}", style="bold #ffb000"), id="editor-title")
            with Horizontal(id="editor-line"):
                yield Select(
                    [(m, m) for m in METHODS],
                    value=req.method,
                    allow_blank=False,
                    id="editor-method",
                )
                yield VarInput(req.url, placeholder="{{baseUrl}}/ruta", id="editor-url")
            yield Static("Params  (una por línea: nombre: valor)", classes="editor-label")
            yield VarTextArea(pairs_to_text(req.params), id="editor-params", classes="editor-pairs")
            yield Static("Headers (uno por línea: Nombre: valor)", classes="editor-label")
            yield VarTextArea(
                pairs_to_text(req.headers), id="editor-headers", classes="editor-pairs"
            )
            with Horizontal(id="editor-body-line"):
                yield Static("Body", classes="editor-label")
                yield Select(
                    [(t, t) for t in BODY_TYPES],
                    value=req.body.type,
                    allow_blank=False,
                    id="editor-body-type",
                )
            yield VarTextArea(body_to_text(req.body), id="editor-body")
            yield Static(id="editor-error")
            yield Static(Text(HINT, style="#8a9bb8"), id="editor-hint")
        yield VarSuggestions()

    def on_mount(self) -> None:
        box = self.suggestions
        for field in (self.url_input, self.params_area, self.headers_area, self.body_area):
            field.var_provider = self._variables
            field.var_box = box
        self._initial = self._snapshot()
        self.url_input.focus()
        self.url_input.cursor_position = len(self.url_input.value)

    # ---- acceso a los campos ---------------------------------------------

    @property
    def url_input(self) -> VarInput:
        return self.query_one("#editor-url", VarInput)

    @property
    def params_area(self) -> VarTextArea:
        return self.query_one("#editor-params", VarTextArea)

    @property
    def headers_area(self) -> VarTextArea:
        return self.query_one("#editor-headers", VarTextArea)

    @property
    def body_area(self) -> VarTextArea:
        return self.query_one("#editor-body", VarTextArea)

    @property
    def suggestions(self) -> VarSuggestions:
        return self.query_one(VarSuggestions)

    @property
    def method_value(self) -> str:
        return str(self.query_one("#editor-method", Select).value)

    @method_value.setter
    def method_value(self, value: str) -> None:
        self.query_one("#editor-method", Select).value = value

    @property
    def body_type_value(self) -> str:
        return str(self.query_one("#editor-body-type", Select).value)

    @body_type_value.setter
    def body_type_value(self, value: str) -> None:
        self.query_one("#editor-body-type", Select).value = value

    def _snapshot(self) -> tuple[str, ...]:
        return (
            self.method_value,
            self.url_input.value,
            self.params_area.text,
            self.headers_area.text,
            self.body_type_value,
            self.body_area.text,
        )

    # ---- acciones --------------------------------------------------------

    def _show_error(self, message: str) -> None:
        self.error_text = message
        self.query_one("#editor-error", Static).update(Text(f"✗ {message}", style="bold red"))

    def action_save(self) -> None:
        self.suggestions.hide()
        try:
            request = build_request(
                self.original,
                method=self.method_value,
                url=self.url_input.value,
                params_text=self.params_area.text,
                headers_text=self.headers_area.text,
                body_type=self.body_type_value,
                body_text=self.body_area.text,
            )
        except FormError as exc:
            self._show_error(str(exc))
            return
        try:
            write_json(self.request_path, request)
        except OSError as exc:
            self._show_error(f"no se pudo guardar: {exc.strerror}")
            return
        self.dismiss(True)

    def action_cancel(self) -> None:
        if self.suggestions.display:
            self.suggestions.hide()
            return
        if self._snapshot() == self._initial:
            self.dismiss(False)
            return

        def discard(ok: bool | None) -> None:
            if ok:
                self.dismiss(False)

        self.app.push_screen(ConfirmScreen("Hay cambios sin guardar. ¿Descartarlos?"), discard)
