"""Vista de carpetas y requests de una colección o carpeta."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.binding import Binding

from kp9.model import FolderMeta, Request
from kp9.store import (
    FOLDER_FILE,
    GROUPS_DIR,
    ContainerNode,
    RequestNode,
    group_dir_of,
    unique_path,
    write_json,
)
from kp9.tui.views.base import Row, TableView
from kp9.tui.views.detail import DetailView
from kp9.tui.widgets import last_text, mark, method_text


class RequestsView(TableView):
    COLUMNS = ("METHOD", "NAME", "URL", "LAST")
    BINDINGS = [Binding("i", "form_edit", "editor")]

    def __init__(self, container_path: Path) -> None:
        super().__init__()
        self.container_path = container_path

    @property
    def group_path(self) -> Path | None:
        return group_dir_of(self.kp9.root, self.container_path)

    @property
    def crumb(self) -> str:
        return self.container_path.name

    def heading(self) -> str:
        rel = self.container_path.relative_to(self.kp9.root / GROUPS_DIR).as_posix()
        return f"Requests({rel})"

    def _container(self) -> ContainerNode | None:
        node = self.kp9.workspace.node_at(self.container_path)
        return node if isinstance(node, ContainerNode) else None

    def rows(self) -> list[Row]:
        node = self._container()
        if node is None:
            return []
        out: list[Row] = []
        for folder in node.children:
            cells = (
                Text("▸", style="bold"),
                mark(f"{folder.name}/", folder.error),
                Text(""),
                Text(""),
            )
            out.append(Row(str(folder.path), cells, folder))
        for req in node.requests:
            last = last_text(self.kp9.history.last_for(self.kp9.rel(req.path)))
            if req.request is not None:
                cells = (
                    method_text(req.request.method),
                    Text(req.request.name),
                    Text(req.request.url),
                    last,
                )
            else:
                cells = (Text("?"), mark(req.name, req.error), Text(req.error or ""), last)
            out.append(Row(str(req.path), cells, req))
        return out

    def edit_target(self, row: Row) -> Path | None:
        target = row.target
        if isinstance(target, ContainerNode):
            if not target.meta_file.exists():
                write_json(target.meta_file, FolderMeta(name=target.path.name))
            return target.meta_file
        return target.path

    def create_item(self, name: str) -> tuple[Path, bool] | None:
        if name.endswith("/"):
            folder_name = name.rstrip("/")
            directory = unique_path(self.container_path, folder_name)
            write_json(directory / FOLDER_FILE, FolderMeta(name=folder_name))
            return directory / FOLDER_FILE, False
        path = unique_path(self.container_path, name, ".json")
        write_json(path, Request(name=name, url="{{baseUrl}}/"))
        return path, True

    def delete_target(self, row: Row) -> Path | None:
        return row.target.path

    def open(self, row: Row) -> None:
        target = row.target
        if isinstance(target, ContainerNode):
            self.kp9.push_view(RequestsView(target.path))
        elif isinstance(target, RequestNode):
            self.kp9.push_view(DetailView(target.path))

    def action_form_edit(self) -> None:
        row = self.selected()
        if row is None or not isinstance(row.target, RequestNode):
            self.kp9.notify("selecciona un request para editarlo", severity="warning")
            return
        self.kp9.open_request_editor(row.target.path)
