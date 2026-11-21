"""Bases de las vistas apilables. Regla: solo View define on_mount."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable

from kp9.tui.widgets import ConfirmScreen, NameScreen

if TYPE_CHECKING:
    from kp9.tui.app import Kp9App

Cell = str | Text


@dataclass
class Row:
    key: str
    cells: tuple[Cell, ...]
    target: Any


class View(Vertical):
    """Una vista de recursos. Las subclases personalizan setup()/reload()."""

    @property
    def kp9(self) -> Kp9App:
        return cast("Kp9App", self.app)

    @property
    def crumb(self) -> str:
        return "?"

    @property
    def group_path(self) -> Path | None:
        return None

    @property
    def has_filter(self) -> bool:
        return False

    def setup(self) -> None:
        """Se llama una vez al montar, antes del primer reload()."""

    def reload(self) -> None:
        """Vuelve a leer los datos desde self.kp9.workspace."""

    def apply_filter(self, text: str) -> None:
        """Filtra el contenido visible."""

    def focus_default(self) -> None:
        self.focus()

    def cancel(self) -> bool:
        """Cancela trabajo en curso; True si había algo que cancelar."""
        return False

    def on_mount(self) -> None:
        self.setup()
        self.reload()
        if self.kp9.current is self:
            self.focus_default()


class TableView(View):
    COLUMNS: tuple[str, ...] = ()
    BINDINGS = [
        Binding("n", "new", "nuevo"),
        Binding("e", "edit", "editar"),
        Binding("d", "delete", "borrar"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[Row] = []
        self._by_key: dict[str, Row] = {}
        self._filter = ""

    def compose(self) -> ComposeResult:
        yield DataTable(cursor_type="row", id="table")

    @property
    def table(self) -> DataTable[Cell]:
        return cast("DataTable[Cell]", self.query_one("#table", DataTable))

    def setup(self) -> None:
        self.table.add_columns(*self.COLUMNS)

    def heading(self) -> str:
        raise NotImplementedError

    def rows(self) -> list[Row]:
        raise NotImplementedError

    def open(self, row: Row) -> None:
        """Acción de Enter sobre una fila."""

    @property
    def has_filter(self) -> bool:
        return bool(self._filter)

    def visible_rows(self) -> list[Row]:
        if not self._filter:
            return list(self._rows)
        needle = self._filter.lower()
        return [r for r in self._rows if any(needle in str(c).lower() for c in r.cells)]

    def selected(self) -> Row | None:
        table = self.table
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return self._by_key.get(key) if key is not None else None

    def reload(self) -> None:
        current = self.selected()
        self._rows = self.rows()
        self._by_key = {r.key: r for r in self._rows}
        self._show(current.key if current else None)

    def apply_filter(self, text: str) -> None:
        current = self.selected()
        self._filter = text.strip()
        self._show(current.key if current else None)

    def _show(self, keep_key: str | None) -> None:
        table = self.table
        table.clear()
        visible = self.visible_rows()
        for row in visible:
            table.add_row(*row.cells, key=row.key)
        title = f"{self.heading()}[{len(visible)}]"
        if self._filter:
            title += f" </{self._filter}>"
        self.border_title = escape(title)
        if keep_key is not None and any(r.key == keep_key for r in visible):
            table.move_cursor(row=table.get_row_index(keep_key))

    def focus_default(self) -> None:
        self.table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        key = event.row_key.value
        row = self._by_key.get(key) if key is not None else None
        if row is not None:
            self.open(row)

    # ---- edición (las subclases implementan los hooks) -------------------

    def edit_target(self, row: Row) -> Path | None:
        return None

    def create_item(self, name: str) -> tuple[Path, bool] | None:
        return None

    def delete_target(self, row: Row) -> Path | None:
        return None

    def action_edit(self) -> None:
        row = self.selected()
        target = self.edit_target(row) if row else None
        if target is None:
            self.kp9.notify("nada que editar aquí", severity="warning")
            return
        self.kp9.edit_file(target)

    def action_new(self) -> None:
        self.kp9.push_screen(
            NameScreen("Nombre (termina en / para crear una carpeta):"), self._on_new_name
        )

    def _on_new_name(self, name: str | None) -> None:
        if not name:
            return
        result = self.create_item(name)
        if result is None:
            self.kp9.notify("no se puede crear aquí", severity="warning")
            return
        path, open_editor = result
        self.kp9.reload_workspace()
        if open_editor:
            self.kp9.edit_file(path)

    def action_delete(self) -> None:
        row = self.selected()
        target = self.delete_target(row) if row else None
        if target is None:
            self.kp9.notify("nada que borrar aquí", severity="warning")
            return
        self.kp9.push_screen(
            ConfirmScreen(f"¿Borrar {self.kp9.rel(target)}?"),
            lambda ok: self.kp9.delete_path(target) if ok else None,
        )
