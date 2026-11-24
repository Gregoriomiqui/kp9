"""Detalle de un request: definición, envío y respuesta."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static, TabbedContent, TabPane
from textual.worker import Worker

from kp9.httpclient import to_curl
from kp9.model import dump
from kp9.resolve import ResolvedRequest, ResolveError
from kp9.runner import NotSendable
from kp9.store import RequestNode, group_dir_of
from kp9.tui.views.base import View
from kp9.tui.widgets import ConfirmScreen, ResponsePanel, method_text

TABS = ("Params", "Headers", "Body", "Auth")


def _json_view(data: Any) -> Syntax:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    return Syntax(text, "json", word_wrap=True, background_color="default")


class DetailView(View):
    can_focus = True
    BINDINGS = [
        Binding("s", "send", "enviar"),
        Binding("ctrl+r", "send", "enviar", show=False),
        Binding("c", "copy_curl", "copiar curl"),
        Binding("y", "copy_body", "copiar body"),
        Binding("e", "edit", "editar"),
        Binding("i", "form_edit", "editor"),
    ]

    def __init__(self, request_path: Path, *, autosend: bool = False) -> None:
        super().__init__()
        self.request_path = request_path
        self.summary_text = ""
        self._autosend = autosend
        self._worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="summary")
        with TabbedContent(id="tabs"):
            for label in TABS:
                with TabPane(label, id=f"tab-{label.lower()}"):
                    yield Static(id=f"def-{label.lower()}")
        yield ResponsePanel(id="response")

    @property
    def panel(self) -> ResponsePanel:
        return self.query_one("#response", ResponsePanel)

    @property
    def crumb(self) -> str:
        return self.request_path.stem

    @property
    def group_path(self) -> Path | None:
        return group_dir_of(self.kp9.root, self.request_path)

    @property
    def in_flight(self) -> bool:
        return self._worker is not None and self._worker.is_running

    @property
    def has_filter(self) -> bool:
        return bool(self.panel.filter_text)

    def apply_filter(self, text: str) -> None:
        self.panel.set_filter(text)

    def node(self) -> RequestNode | None:
        node = self.kp9.workspace.node_at(self.request_path)
        return node if isinstance(node, RequestNode) else None

    def setup(self) -> None:
        if self._autosend:
            self.call_after_refresh(self.action_send)

    def reload(self) -> None:
        self.border_title = escape(f"Detalle({self.kp9.rel(self.request_path)})")
        summary = self.query_one("#summary", Static)
        node = self.node()
        if node is None or node.request is None:
            message = node.error if node is not None else "el request ya no existe"
            self.summary_text = f"⚠ {message}"
            summary.update(Text(self.summary_text, style="bold red"))
            return
        req = node.request
        self.summary_text = f"{req.method}  {req.url}"
        if req.description:
            self.summary_text += f"\n{req.description}"
        summary.update(
            Text.assemble(
                method_text(req.method),
                f"  {req.url}",
                f"\n{req.description}" if req.description else "",
            )
        )
        self.query_one("#def-params", Static).update(_json_view(req.params))
        self.query_one("#def-headers", Static).update(_json_view(req.headers))
        self.query_one("#def-body", Static).update(_json_view(dump(req.body)))
        self.query_one("#def-auth", Static).update(_json_view(dump(req.auth)))

    # ---- envío ----------------------------------------------------------

    def _fail(self, message: str) -> None:
        self.panel.show_error(message)
        self.kp9.notify(f"{message}\n(E: entornos)", title="no se envió", severity="error")

    def _prepare(self) -> ResolvedRequest | None:
        node = self.node()
        if node is None:
            self._fail("el request ya no existe")
            return None
        try:
            return self.kp9.runner.prepare(node, self.kp9.env_name)
        except (ResolveError, NotSendable) as exc:
            self._fail(str(exc))
            return None

    def action_send(self) -> None:
        if self.in_flight:
            return
        resolved = self._prepare()
        if resolved is None:
            return
        env = self.kp9.env_name
        if self.kp9.runner.needs_confirmation(resolved, env):
            question = (
                f"El entorno '{env}' está protegido.\n¿Enviar {resolved.method} {resolved.url}?"
            )
            self.kp9.push_screen(
                ConfirmScreen(question), lambda ok: self._start(resolved) if ok else None
            )
        else:
            self._start(resolved)

    def _start(self, resolved: ResolvedRequest) -> None:
        self.panel.show_pending()
        self._worker = self.run_worker(self._send(resolved), exclusive=True, group="send")

    async def _send(self, resolved: ResolvedRequest) -> None:
        try:
            outcome = await self.kp9.runner.execute(resolved, self.kp9.env_name, self.request_path)
        except Exception as exc:  # p. ej. secrets.json roto entre preparar y enviar
            self.panel.show_error(str(exc) or type(exc).__name__)
            return
        if outcome.response is not None:
            self.panel.show_response(outcome.response)
        else:
            self.panel.show_error(outcome.error or "error desconocido")

    def cancel(self) -> bool:
        if self._worker is not None and self._worker.is_running:
            self._worker.cancel()
            self.panel.show_error("cancelado")
            return True
        return False

    # ---- copiar ---------------------------------------------------------

    def action_form_edit(self) -> None:
        self.kp9.open_request_editor(self.request_path)

    def action_edit(self) -> None:
        self.kp9.edit_file(self.request_path)

    def action_copy_curl(self) -> None:
        resolved = self._prepare()
        if resolved is not None:
            self.run_worker(self._copy_curl(resolved), group="curl")

    async def _copy_curl(self, resolved: ResolvedRequest) -> None:
        try:
            authed = await self.kp9.runner.authorize(resolved)
        except Exception as exc:
            self.kp9.notify(str(exc) or type(exc).__name__, severity="error")
            return
        self.kp9.copy_to_clipboard(to_curl(authed))
        self.kp9.notify("request copiado como curl")

    def action_copy_body(self) -> None:
        response = self.panel.current_response
        if response is None:
            self.kp9.notify("no hay respuesta para copiar", severity="warning")
            return
        self.kp9.copy_to_clipboard(response.pretty())
        self.kp9.notify("body copiado")
