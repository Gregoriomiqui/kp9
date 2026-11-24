"""Árbol Grupo → Colección → Carpeta → Request: el sidebar ocultable, como en Postman."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from kp9.store import ContainerNode, RequestNode, group_dir_of
from kp9.tui.views.base import View
from kp9.tui.widgets import mark, method_text

Node = TreeNode[Path]


def _request_label(req: RequestNode) -> Text:
    if req.request is None:
        return mark(req.name, req.error)
    method = req.request.method
    label = method_text(method)
    label.append(" " * max(1, 5 - len(method)))
    label.append(req.request.name)
    return label


def _matches(req: RequestNode, needle: str) -> bool:
    # como Postman: busca por nombre (la URL trae {{variables}} que dan falsos positivos)
    return needle in req.name.lower()


class TreeView(View):
    """Árbol navegable. Recuerda qué nodos están plegados y dónde está el cursor."""

    BINDINGS = [
        Binding("right,l", "expand", "desplegar", show=False),
        Binding("left,h", "collapse", "plegar / subir", show=False),
        Binding("j", "cursor_down", "bajar", show=False),
        Binding("k", "cursor_up", "subir", show=False),
        Binding("e", "edit", "editar"),
        Binding("i", "form_edit", "editor"),
    ]

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._filter = ""
        self._collapsed: set[Path] = set()

    def compose(self) -> ComposeResult:
        tree: Tree[Path] = Tree("workspace", id="tree")
        tree.show_root = False
        tree.guide_depth = 2
        yield tree

    # ---- propiedades de View --------------------------------------------

    @property
    def tree_widget(self) -> Tree[Path]:
        return self.query_one("#tree", Tree)

    @property
    def crumb(self) -> str:
        return "árbol"

    @property
    def group_path(self) -> Path | None:
        path = self.cursor_path()
        return group_dir_of(self.kp9.root, path) if path else None

    @property
    def has_filter(self) -> bool:
        return bool(self._filter)

    def focus_default(self) -> None:
        self.tree_widget.focus()

    # ---- construcción ----------------------------------------------------

    def reload(self) -> None:
        if not self._filter:
            self._collapsed = self._current_collapsed()
        cursor = self.cursor_path()
        self.border_title = "Árbol" + (f" /{self._filter}" if self._filter else "")
        tree = self.tree_widget
        tree.clear()
        needle = self._filter.lower()
        for group in self.kp9.workspace.groups:
            self._add_container(tree.root, group, needle)
        self.move_cursor_to(cursor)

    def _add_container(self, parent: Node, container: ContainerNode, needle: str) -> bool:
        """Agrega el contenedor si tiene algo que mostrar; True si lo agregó."""
        node = parent.add(mark(container.name, container.error), data=container.path)
        shown = not needle
        for child in container.children:
            shown = self._add_container(node, child, needle) or shown
        for req in container.requests:
            if not needle or _matches(req, needle):
                node.add_leaf(_request_label(req), data=req.path)
                shown = True
        if not shown:
            node.remove()
            return False
        if needle or container.path not in self._collapsed:
            node.expand()
        return True

    def _current_collapsed(self) -> set[Path]:
        collapsed = set(self._collapsed)
        for node in self._walk(self.tree_widget.root, only_visible=False):
            if node.data is None or not node.allow_expand:
                continue
            if node.is_expanded:
                collapsed.discard(node.data)
            else:
                collapsed.add(node.data)
        return collapsed

    def _walk(self, node: Node, only_visible: bool = True) -> Iterator[Node]:
        for child in node.children:
            yield child
            if child.is_expanded or not only_visible:
                yield from self._walk(child, only_visible)

    # ---- API para la app y los tests -------------------------------------

    def visible_lines(self) -> list[str]:
        """Texto plano de las líneas visibles, con dos espacios por nivel."""
        return [
            "  " * _depth(node)
            + (node.label.plain if isinstance(node.label, Text) else str(node.label))
            for node in self._walk(self.tree_widget.root)
        ]

    def cursor_path(self) -> Path | None:
        try:
            node = self.tree_widget.cursor_node
        except Exception:  # aún sin montar
            return None
        return node.data if node is not None else None

    def move_cursor_to(self, path: Path | None) -> None:
        """Pone el cursor en `path`; si está oculto (plegado o filtrado), en su ancestro visible."""
        best: int | None = None
        best_depth = -1
        for i, node in enumerate(self._walk(self.tree_widget.root)):
            if node.data is None or path is None:
                continue
            if node.data == path:
                best = i
                break
            if node.data in path.parents and len(node.data.parts) > best_depth:
                best, best_depth = i, len(node.data.parts)
        self.tree_widget.cursor_line = best if best is not None else 0

    def apply_filter(self, text: str) -> None:
        if not self._filter:
            self._collapsed = self._current_collapsed()
        self._filter = text.strip()
        self.reload()
        self.kp9.refresh_chrome()

    # ---- acciones --------------------------------------------------------

    def on_tree_node_selected(self, event: Tree.NodeSelected[Path]) -> None:
        event.stop()
        path = event.node.data
        if path is not None and isinstance(self.kp9.workspace.node_at(path), RequestNode):
            self.kp9.open_request(path)

    def action_expand(self) -> None:
        node = self.tree_widget.cursor_node
        if node is not None and node.allow_expand:
            node.expand()

    def action_collapse(self) -> None:
        node = self.tree_widget.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
        elif node.parent is not None and node.parent is not self.tree_widget.root:
            self.tree_widget.move_cursor(node.parent)

    def action_cursor_down(self) -> None:
        self.tree_widget.action_cursor_down()

    def action_cursor_up(self) -> None:
        self.tree_widget.action_cursor_up()

    def action_form_edit(self) -> None:
        path = self.cursor_path()
        if path is None:
            return
        self.kp9.open_request_editor(path)

    def action_edit(self) -> None:
        path = self.cursor_path()
        target = self.kp9.workspace.node_at(path) if path else None
        if isinstance(target, ContainerNode):
            self.kp9.edit_file(target.meta_file)
        elif isinstance(target, RequestNode):
            self.kp9.edit_file(target.path)
        else:
            self.kp9.notify("nada que editar aquí", severity="warning")


def _depth(node: Node) -> int:
    depth = 0
    parent = node.parent
    while parent is not None and parent.parent is not None:
        depth += 1
        parent = parent.parent
    return depth
