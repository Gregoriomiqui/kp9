"""Vista de entornos."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from kp9.model import Environment, SecretRef
from kp9.redact import MASK
from kp9.store import ENVIRONMENTS_DIR, unique_path, write_json
from kp9.tui.views.base import Row, TableView


class EnvsView(TableView):
    COLUMNS = ("ACTIVO", "NAME", "PROTEGIDO", "VARIABLES")

    def __init__(self) -> None:
        super().__init__()
        self.vars_text = ""

    def compose(self) -> ComposeResult:
        yield DataTable(cursor_type="row", id="table")
        yield Static(id="vars")

    @property
    def crumb(self) -> str:
        return "entornos"

    def heading(self) -> str:
        return "Entornos"

    def rows(self) -> list[Row]:
        envs = self.kp9.workspace.environments
        return [
            Row(
                name,
                (
                    Text("●", style="bold green") if name == self.kp9.env_name else Text(""),
                    Text(name),
                    Text("sí", style="bold red") if envs[name].protected else Text(""),
                    Text(str(len(envs[name].variables))),
                ),
                name,
            )
            for name in sorted(envs)
        ]

    def reload(self) -> None:
        super().reload()
        row = self.selected()
        self._show_vars(row.target if row else None)

    def edit_target(self, row: Row) -> Path | None:
        return self.kp9.workspace.env_files.get(row.target)

    def create_item(self, name: str) -> tuple[Path, bool] | None:
        path = unique_path(self.kp9.root / ENVIRONMENTS_DIR, name, ".json")
        write_json(path, Environment(name=name))
        return path, True

    def delete_target(self, row: Row) -> Path | None:
        return self.kp9.workspace.env_files.get(row.target)

    def open(self, row: Row) -> None:
        self.kp9.set_env(row.target)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_vars(event.row_key.value)

    def _show_vars(self, name: str | None) -> None:
        env = self.kp9.workspace.environments.get(name) if name else None
        if env is None:
            self.vars_text = ""
        else:
            lines = [
                f"{key} = {MASK if isinstance(value, SecretRef) else value}"
                for key, value in sorted(env.variables.items())
            ]
            self.vars_text = "\n".join(lines) or "(sin variables)"
        self.query_one("#vars", Static).update(Text(self.vars_text))
