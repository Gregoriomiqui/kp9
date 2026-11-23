"""Línea de comandos de kp9."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from kp9.importer.postman import (
    PostmanImportError,
    format_report,
    import_collection,
    import_environment,
)
from kp9.store import WORKSPACE_FILE, WorkspaceNotFound, find_workspace_root, init_workspace

app = typer.Typer(add_completion=False, help="kp9 — cliente HTTP para la terminal estilo k9s.")

WorkspaceOpt = Annotated[
    Path | None,
    typer.Option("--workspace", "-w", help="Carpeta del workspace (por defecto, la actual)."),
]


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(1)


def default_home() -> Path:
    """Workspace por defecto: `$KP9_HOME` o `~/kp9`."""
    env = os.environ.get("KP9_HOME")
    return Path(env).expanduser() if env else Path.home() / "kp9"


def _root(workspace: Path | None) -> Path:
    if workspace is not None:
        try:
            return find_workspace_root(workspace)
        except WorkspaceNotFound as exc:
            raise _fail(str(exc)) from exc
    try:
        return find_workspace_root(Path.cwd())
    except WorkspaceNotFound:
        pass
    # fuera de un workspace: usa (y crea la primera vez) el workspace por defecto
    home = default_home()
    if (home / WORKSPACE_FILE).is_file():
        return home.resolve()
    root = init_workspace(home, "kp9")
    typer.echo(f"Workspace creado en {root}")
    return root


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _fail(f"{path}: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise _fail(f"{path}: no es texto UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise _fail(f"{path}:{exc.lineno}:{exc.colno}: {exc.msg}") from exc


def _launch_tui(root: Path) -> None:
    from kp9.tui.app import Kp9App

    Kp9App(root).run()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, workspace: WorkspaceOpt = None) -> None:
    """Sin subcomando abre la TUI."""
    if ctx.invoked_subcommand is None:
        _launch_tui(_root(workspace))


@app.command()
def init(
    path: Annotated[Path, typer.Argument(help="Carpeta del nuevo workspace.")] = Path("."),
    name: Annotated[str | None, typer.Option(help="Nombre del workspace.")] = None,
) -> None:
    """Crea la estructura base de un workspace."""
    try:
        root = init_workspace(path, name or path.resolve().name)
    except FileExistsError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"Workspace creado en {root}")


@app.command("import")
def import_(
    file: Annotated[Path, typer.Argument(help="Colección Postman v2.1 (.json).")],
    group: Annotated[str, typer.Option("--group", "-g", help="Grupo destino.")],
    env: Annotated[
        list[Path] | None, typer.Option("--env", "-e", help="Entorno Postman (repetible).")
    ] = None,
    workspace: WorkspaceOpt = None,
) -> None:
    """Importa una colección (y entornos opcionales) de Postman."""
    root = _root(workspace)
    try:
        reports = [import_collection(_read_json(file), root, group)]
        for env_file in env or []:
            reports.append(import_environment(_read_json(env_file), root))
    except PostmanImportError as exc:
        raise _fail(str(exc)) from exc
    for report in reports:
        typer.echo(format_report(report))
