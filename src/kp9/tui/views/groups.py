"""Vistas de grupos y colecciones."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text

from kp9.model import CollectionMeta, GroupMeta
from kp9.store import (
    COLLECTION_FILE,
    GROUP_FILE,
    GROUPS_DIR,
    ContainerNode,
    count_requests,
    unique_path,
    write_json,
)
from kp9.tui.views.base import Row, TableView
from kp9.tui.views.requests import RequestsView
from kp9.tui.widgets import mark


def _description(node: ContainerNode) -> Text:
    # Text explícito: un str en DataTable se interpreta como markup ("[/]" rompe la vista)
    return Text(node.meta.description if node.meta else (node.error or ""))


class GroupsView(TableView):
    COLUMNS = ("NAME", "COLECCIONES", "DESCRIPCIÓN")

    @property
    def crumb(self) -> str:
        return "grupos"

    def heading(self) -> str:
        return "Grupos"

    def rows(self) -> list[Row]:
        return [
            Row(str(g.path), (mark(g.name, g.error), str(len(g.children)), _description(g)), g)
            for g in self.kp9.workspace.groups
        ]

    def edit_target(self, row: Row) -> Path | None:
        return row.target.meta_file

    def create_item(self, name: str) -> tuple[Path, bool] | None:
        directory = unique_path(self.kp9.root / GROUPS_DIR, name)
        write_json(directory / GROUP_FILE, GroupMeta(name=name))
        return directory / GROUP_FILE, True

    def delete_target(self, row: Row) -> Path | None:
        return row.target.path

    def open(self, row: Row) -> None:
        self.kp9.push_view(CollectionsView(row.target.path))


class CollectionsView(TableView):
    COLUMNS = ("NAME", "REQUESTS", "DESCRIPCIÓN")

    def __init__(self, group_path: Path) -> None:
        super().__init__()
        self._group_path = group_path

    @property
    def group_path(self) -> Path | None:
        return self._group_path

    @property
    def crumb(self) -> str:
        return self._group_path.name

    def heading(self) -> str:
        return f"Colecciones({self._group_path.name})"

    def _group(self) -> ContainerNode | None:
        node = self.kp9.workspace.node_at(self._group_path)
        return node if isinstance(node, ContainerNode) else None

    def rows(self) -> list[Row]:
        group = self._group()
        if group is None:
            return []
        return [
            Row(str(c.path), (mark(c.name, c.error), str(count_requests(c)), _description(c)), c)
            for c in group.children
        ]

    def edit_target(self, row: Row) -> Path | None:
        return row.target.meta_file

    def create_item(self, name: str) -> tuple[Path, bool] | None:
        directory = unique_path(self._group_path, name)
        write_json(directory / COLLECTION_FILE, CollectionMeta(name=name))
        return directory / COLLECTION_FILE, True

    def delete_target(self, row: Row) -> Path | None:
        return row.target.path

    def open(self, row: Row) -> None:
        self.kp9.push_view(RequestsView(row.target.path))
