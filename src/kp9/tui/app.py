"""Aplicación Textual de kp9."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import httpx
from rich.text import Text
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.suggester import SuggestFromList
from textual.widgets import Input, Static
from watchfiles import Change, awatch

from kp9.auth import TokenCache
from kp9.history import History, HistoryEntry
from kp9.importer.postman import (
    PostmanImportError,
    format_report,
    import_collection,
    import_environment,
    is_environment,
)
from kp9.runner import Runner
from kp9.store import (
    GROUPS_DIR,
    LOCAL_DIR,
    ContainerNode,
    RequestNode,
    WorkspaceNotFound,
    group_dir_of,
    load_workspace,
    model_for_file,
    read_model,
    slugify,
)
from kp9.tui import editor
from kp9.tui.request_editor import RequestEditorScreen
from kp9.tui.views.base import View
from kp9.tui.views.detail import DetailView
from kp9.tui.views.envs import EnvsView
from kp9.tui.views.groups import CollectionsView, GroupsView
from kp9.tui.views.history import HistoryView
from kp9.tui.views.requests import RequestsView
from kp9.tui.views.tree import TreeView
from kp9.tui.widgets import ConfirmScreen, HelpScreen
from kp9.variables import VariableInfo

SHORTCUTS = "<1> grupos  <2> colecciones  <E> env  <t> árbol  <ctrl+b> ocultar  <h> historial  <:> comando  </> filtro  <?> ayuda"


def _relevant_change(change: Change, path: str) -> bool:
    parts = Path(path).parts
    return ".kp9" not in parts and ".git" not in parts


class Kp9App(App[None]):
    CSS_PATH = "kp9.tcss"
    TITLE = "kp9"
    BINDINGS = [
        Binding("1", "goto_groups", "grupos"),
        Binding("2", "goto_collections", "colecciones"),
        Binding("E", "goto_envs", "entornos"),
        Binding("h", "goto_history", "historial"),
        Binding("t", "goto_tree", "árbol"),
        Binding("ctrl+b", "toggle_sidebar", "mostrar/ocultar árbol"),
        Binding("colon", "prompt(':')", "comando"),
        Binding("slash", "prompt('/')", "filtrar"),
        Binding("question_mark", "help", "ayuda"),
        Binding("escape", "back", "volver"),
        Binding("ctrl+c", "quit", "salir", show=False),
    ]

    def __init__(
        self,
        root: Path,
        *,
        client: httpx.AsyncClient | None = None,
        environ: Mapping[str, str] | None = None,
        watch: bool = True,
    ) -> None:
        super().__init__()
        self.root = root.resolve()
        self.workspace = load_workspace(self.root)
        self.history = History(self.root / LOCAL_DIR / "history.db")
        self.client = client or httpx.AsyncClient(follow_redirects=True)
        self.runner = Runner(self.workspace, self.history, self.client, TokenCache(), environ)
        self.env_name = self._initial_env()
        self.topbar_text = ""
        self.crumbs_text = ""
        self._stack: list[View] = []
        self._last_group: Path | None = None
        self._prompt_mode: str | None = None
        self._filter_target: View | None = None
        self._watch = watch

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="main"):
            yield TreeView(id="sidebar")
            yield Vertical(id="body")
        yield Input(id="prompt")
        yield Static(id="crumbs")

    def on_mount(self) -> None:
        self.push_view(GroupsView())
        if self._watch:
            self.run_worker(self._watch_files(), group="watch", exit_on_error=False)

    async def _watch_files(self) -> None:
        async for _changes in awatch(self.root, watch_filter=_relevant_change, debounce=300):
            self.reload_workspace()

    async def on_unmount(self) -> None:
        await self.client.aclose()
        self.history.close()

    # ---- pila de vistas -------------------------------------------------

    @property
    def current(self) -> View | None:
        return self._stack[-1] if self._stack else None

    @property
    def stack(self) -> tuple[View, ...]:
        return tuple(self._stack)

    @property
    def sidebar(self) -> TreeView:
        return self.query_one("#sidebar", TreeView)

    @property
    def sidebar_focused(self) -> bool:
        sidebar = self.sidebar
        return sidebar.display and sidebar.has_focus_within

    def push_view(self, view: View) -> None:
        if self._stack:
            self._stack[-1].display = False
        self._stack.append(view)
        self.query_one("#body", Vertical).mount(view)
        if isinstance(view, DetailView) and not self.sidebar_focused:
            self.sidebar.move_cursor_to(view.request_path)
        self.refresh_chrome()

    def pop_view(self) -> bool:
        if len(self._stack) <= 1:
            return False
        self._stack.pop().remove()
        previous = self._stack[-1]
        previous.display = True
        previous.reload()
        previous.focus_default()
        self.refresh_chrome()
        return True

    def reset_to(self, *views: View) -> None:
        for view in self._stack:
            view.remove()
        self._stack.clear()
        for view in views:
            self.push_view(view)

    # ---- contexto -------------------------------------------------------

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    @property
    def current_group(self) -> Path | None:
        for view in reversed(self._stack):
            group = view.group_path
            if group is not None:
                self._last_group = group
                return group
        return self._last_group

    def _default_group(self) -> Path | None:
        name = self.workspace.config.defaultGroup
        if not name:
            return None
        path = self.root / GROUPS_DIR / slugify(name)
        return path if isinstance(self.workspace.node_at(path), ContainerNode) else None

    def _initial_env(self) -> str | None:
        envs = self.workspace.environments
        default = self.workspace.config.defaultEnv
        if default in envs:
            return default
        return sorted(envs)[0] if envs else None

    def set_env(self, name: str) -> bool:
        if name not in self.workspace.environments:
            self.notify(f"el entorno '{name}' no existe", severity="error")
            return False
        self.env_name = name
        self.refresh_chrome()
        if self.current is not None:
            self.current.reload()
        self.notify(f"entorno activo: {name}")
        return True

    def refresh_chrome(self) -> None:
        env = self.runner.environment(self.env_name)
        protected = bool(env and env.protected)
        group_path = self.current_group
        group = self.workspace.node_at(group_path) if group_path else None
        group_name = group.name if isinstance(group, ContainerNode) else "—"
        env_label = f"<{self.env_name}>" if self.env_name else "<sin entorno>"
        if protected:
            env_label += " PROTEGIDO"
        self.topbar_text = (
            f"Workspace: {self.workspace.config.name}   Env: {env_label}   Grupo: {group_name}"
            f"\n{SHORTCUTS}"
        )
        topbar = self.query_one("#topbar", Static)
        topbar.update(Text(self.topbar_text))
        topbar.set_class(protected, "protected")
        self.crumbs_text = " ".join(f"<{view.crumb}>" for view in self._stack)
        self.query_one("#crumbs", Static).update(Text(self.crumbs_text))

    def reload_workspace(self) -> None:
        try:
            workspace = load_workspace(self.root)
        except WorkspaceNotFound as exc:
            self.notify(str(exc), severity="error")
            return
        self.workspace = workspace
        self.runner.workspace = workspace
        if self.env_name and self.env_name not in workspace.environments:
            self.notify(
                f"el entorno '{self.env_name}' ya no existe; sin entorno activo", severity="warning"
            )
            self.env_name = None
        for view in self._stack:
            view.reload()
        self.sidebar.reload()
        self.refresh_chrome()

    # ---- prompt y comandos ----------------------------------------------

    def _command_suggestions(self) -> list[str]:
        out = ["groups", "tree", "history", "env", "import ", "q"]
        out += [f"env {name}" for name in sorted(self.workspace.environments)]
        out += [f"col {c.path.name}" for g in self.workspace.groups for c in g.children]
        return out

    def action_prompt(self, mode: str) -> None:
        prompt = self.query_one("#prompt", Input)
        self._prompt_mode = mode
        self._filter_target = self.sidebar if self.sidebar_focused else self.current
        prompt.suggester = (
            SuggestFromList(self._command_suggestions(), case_sensitive=False)
            if mode == ":"
            else None
        )
        prompt.placeholder = "comando…" if mode == ":" else "filtro…"
        prompt.value = ""
        prompt.display = True
        prompt.focus()

    def close_prompt(self) -> None:
        self._prompt_mode = None
        prompt = self.query_one("#prompt", Input)
        prompt.value = ""
        prompt.display = False
        target = self._filter_target or self.current
        if target is not None:
            target.focus_default()

    def on_input_changed(self, event: Input.Changed) -> None:
        target = self._filter_target
        if event.input.id == "prompt" and self._prompt_mode == "/" and target is not None:
            target.apply_filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "prompt":
            return
        event.stop()
        mode, value, target = self._prompt_mode, event.value, self._filter_target
        self.close_prompt()
        if mode == ":":
            self.run_command(value)
        elif mode == "/" and target is not None:
            target.apply_filter(value)

    def _find_collection(self, name: str) -> ContainerNode | None:
        needle = name.strip().lower()
        current = self.current_group
        groups = sorted(self.workspace.groups, key=lambda g: g.path != current)
        for group in groups:
            for col in group.children:
                if needle in (col.path.name.lower(), col.name.lower()):
                    return col
        return None

    def run_command(self, text: str) -> None:
        command, _, arg = text.strip().partition(" ")
        arg = arg.strip()
        if command in ("q", "quit"):
            self.exit()
        elif command == "groups":
            self.action_goto_groups()
        elif command == "history":
            self.action_goto_history()
        elif command == "tree":
            self.action_goto_tree()
        elif command == "env":
            if arg:
                self.set_env(arg)
            else:
                self.action_goto_envs()
        elif command == "col":
            col = self._find_collection(arg)
            if col is None:
                self.notify(f"colección '{arg}' no encontrada", severity="error")
                return
            self.reset_to(GroupsView(), CollectionsView(col.path.parent), RequestsView(col.path))
        elif command == "import":
            self.import_file(arg)
        elif command:
            self.notify(f"comando desconocido: {command}", severity="error")

    def rerun(self, entry: HistoryEntry) -> None:
        if not entry.request_path:
            self.notify("la ejecución no está asociada a un archivo de request", severity="error")
            return
        path = self.root / entry.request_path
        if not isinstance(self.workspace.node_at(path), RequestNode):
            self.notify(f"{entry.request_path} ya no existe", severity="error")
            return
        if entry.env != self.env_name:
            self.notify(f"se re-ejecuta con el entorno activo ({self.env_name or 'ninguno'})")
        self.push_view(DetailView(path, autosend=True))

    def open_request(self, path: Path) -> None:
        """Abre un request desde el árbol: grupos > colección > carpetas > detalle."""
        group = group_dir_of(self.root, path)
        if group is None:
            return
        views: list[View] = [GroupsView(), CollectionsView(group)]
        containers = [p for p in reversed(path.parents) if group in p.parents]
        views += [RequestsView(p) for p in containers]
        self.reset_to(*views, DetailView(path))

    # ---- archivos -------------------------------------------------------

    def open_request_editor(self, path: Path) -> None:
        """Editor integrado (con autocompletado de {{variables}}) para un request."""
        node = self.workspace.node_at(path)
        if not isinstance(node, RequestNode) or node.request is None:
            message = node.error if isinstance(node, RequestNode) and node.error else None
            self.notify(message or "selecciona un request para editarlo", severity="warning")
            return

        def variables() -> list[VariableInfo]:
            current = self.workspace.node_at(path)
            return self.runner.variables_for(
                current if isinstance(current, RequestNode) else node, self.env_name
            )

        def saved(ok: bool | None) -> None:
            if ok:
                self.reload_workspace()
                self.notify(f"guardado: {self.rel(path)}")

        self.push_screen(RequestEditorScreen(path, node.request, variables), saved)

    def edit_file(self, path: Path) -> None:
        try:
            editor.open_in_editor(self, path)
        except FileNotFoundError:
            self.notify(
                f"no se encontró el editor '{editor.editor_command()[0]}'", severity="error"
            )
            return
        except SuspendNotSupported:
            self.notify("este terminal no permite abrir el editor", severity="error")
            return
        self.reload_workspace()
        _, error = read_model(path, model_for_file(self.root, path))
        if error:
            self.push_screen(
                ConfirmScreen(f"{error}\n\n¿Reabrir el editor?"),
                lambda ok: self.edit_file(path) if ok else None,
            )

    def delete_path(self, path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        self.reload_workspace()
        self.notify(f"borrado: {self.rel(path)}")

    def _import_group(self) -> str | None:
        group = self.current_group
        if group is not None:
            return group.name
        return self.workspace.config.defaultGroup

    def import_file(self, arg: str) -> None:
        if not arg:
            self.notify("uso: :import <archivo>", severity="error")
            return
        path = Path(arg).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            self.notify(f"{path}: {exc.strerror}", severity="error")
            return
        except UnicodeDecodeError:
            self.notify(f"{path}: no es texto UTF-8", severity="error")
            return
        except json.JSONDecodeError as exc:
            self.notify(f"{path}:{exc.lineno}:{exc.colno}: {exc.msg}", severity="error")
            return
        try:
            if is_environment(data):
                report = import_environment(data, self.root)
            else:
                group = self._import_group()
                if group is None:
                    self.notify(
                        "abre un grupo o define defaultGroup en workspace.json", severity="error"
                    )
                    return
                report = import_collection(data, self.root, group)
        except PostmanImportError as exc:
            self.notify(str(exc), severity="error")
            return
        self.reload_workspace()
        self.notify(format_report(report), title="importación", timeout=10)

    # ---- acciones -------------------------------------------------------

    def action_goto_envs(self) -> None:
        self.push_view(EnvsView())

    def action_goto_history(self) -> None:
        self.push_view(HistoryView())

    def action_goto_tree(self) -> None:
        """Muestra y enfoca el árbol; si ya tenía el foco, lo oculta."""
        sidebar = self.sidebar
        if self.sidebar_focused:
            self.hide_sidebar()
            return
        sidebar.display = True
        sidebar.focus_default()

    def action_toggle_sidebar(self) -> None:
        if self.sidebar.display:
            self.hide_sidebar()
        else:
            self.sidebar.display = True
            self.sidebar.focus_default()

    def hide_sidebar(self) -> None:
        focused = self.sidebar_focused
        self.sidebar.display = False
        if focused and self.current is not None:
            self.current.focus_default()

    def focus_main(self) -> None:
        if self.current is not None:
            self.current.focus_default()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_goto_groups(self) -> None:
        self.reset_to(GroupsView())

    def action_goto_collections(self) -> None:
        group = self.current_group or self._default_group()
        if group is None:
            self.notify(
                "Abre un grupo primero (o define defaultGroup en workspace.json)",
                severity="warning",
            )
            return
        self.reset_to(GroupsView(), CollectionsView(group))

    async def action_back(self) -> None:
        if self.query_one("#prompt", Input).display:
            self.close_prompt()
            return
        if self.sidebar_focused:
            if self.sidebar.has_filter:
                self.sidebar.apply_filter("")
            else:
                self.focus_main()
            return
        view = self.current
        if view is None:
            return
        if view.cancel():
            return
        if view.has_filter:
            view.apply_filter("")
            return
        self.pop_view()
