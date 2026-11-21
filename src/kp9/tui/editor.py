"""Apertura de archivos en $EDITOR suspendiendo la TUI."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from textual.app import App


def editor_command() -> list[str]:
    return shlex.split(os.environ.get("EDITOR") or "vi")


def open_in_editor(app: App[Any], path: Path) -> None:
    with app.suspend():
        subprocess.run([*editor_command(), str(path)], check=False)
