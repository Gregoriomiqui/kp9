"""Autocompletado de `{{variables}}` para Input y TextArea, al estilo Postman."""

from __future__ import annotations

from collections.abc import Callable

from rich.text import Text
from textual import events
from textual.geometry import Offset
from textual.widgets import Input, OptionList, TextArea
from textual.widgets.option_list import Option

from kp9.variables import VariableInfo, completion_prefix, filter_variables

VariablesProvider = Callable[[], list[VariableInfo]]
_KEYS = ("up", "down", "tab", "enter", "escape")
MAX_VISIBLE = 8


class VarSuggestions(OptionList):
    """Lista flotante de variables. No toma el foco: el campo que escribe la controla."""

    can_focus = False

    def __init__(self) -> None:
        super().__init__(id="var-suggestions")
        self._items: list[VariableInfo] = []
        self.display = False

    def names(self) -> list[str]:
        return [item.name for item in self._items] if self.display else []

    def rendered_lines(self) -> list[str]:
        return [_prompt(item, self._name_width()).plain for item in self._items]

    def _name_width(self) -> int:
        return max((len(item.name) for item in self._items), default=0)

    def show(self, items: list[VariableInfo], at: Offset) -> None:
        self._items = items
        width = self._name_width()
        self.clear_options()
        self.add_options([Option(_prompt(item, width)) for item in items])
        self.highlighted = 0
        self.styles.height = min(len(items), MAX_VISIBLE) + 2
        self.styles.offset = (at.x, at.y + 1)
        self.display = True

    def hide(self) -> None:
        self.display = False
        self._items = []

    def move(self, delta: int) -> None:
        if self._items:
            current = self.highlighted or 0
            self.highlighted = (current + delta) % len(self._items)

    def selected(self) -> VariableInfo | None:
        if not self.display or not self._items:
            return None
        return self._items[self.highlighted or 0]


def _prompt(item: VariableInfo, width: int) -> Text:
    text = Text()
    text.append(item.name.ljust(width), style="bold #00e5ff")
    text.append("  ")
    value = item.display
    text.append(value if len(value) <= 40 else value[:39] + "…", style="#c7d0e0")
    text.append(f"  {item.source}", style="italic #8a9bb8")
    return text


class _Completion:
    """Lógica común. Las subclases dan el texto alrededor del cursor y cómo reemplazarlo."""

    var_provider: VariablesProvider | None = None
    var_box: VarSuggestions | None = None

    def _kp9_around_cursor(self) -> tuple[str, str]:
        raise NotImplementedError

    def _kp9_replace_before_cursor(self, count: int, text: str, skip_after: int) -> None:
        raise NotImplementedError

    def _kp9_suggest_at(self) -> Offset:
        raise NotImplementedError

    def refresh_suggestions(self) -> None:
        box = self.var_box
        if box is None or self.var_provider is None:
            return
        before, _ = self._kp9_around_cursor()
        prefix = completion_prefix(before)
        items = filter_variables(self.var_provider(), prefix) if prefix is not None else []
        if items:
            box.show(items, self._kp9_suggest_at())
        else:
            box.hide()

    def accept_suggestion(self) -> bool:
        box = self.var_box
        info = box.selected() if box else None
        if box is None or info is None:
            return False
        before, after = self._kp9_around_cursor()
        prefix = completion_prefix(before) or ""
        closing = after.startswith("}}")
        self._kp9_replace_before_cursor(
            len(prefix), info.name + ("" if closing else "}}"), 2 if closing else 0
        )
        box.hide()
        return True

    def completion_key(self, event: events.Key) -> bool:
        """Maneja la tecla si la lista está abierta. True si la consumió."""
        box = self.var_box
        if box is None or not box.display or event.key not in _KEYS:
            return False
        if event.key == "up":
            box.move(-1)
        elif event.key == "down":
            box.move(1)
        elif event.key == "escape":
            box.hide()
        else:
            self.accept_suggestion()
        event.stop()
        event.prevent_default()
        return True


class VarInput(_Completion, Input):
    def _kp9_around_cursor(self) -> tuple[str, str]:
        return self.value[: self.cursor_position], self.value[self.cursor_position :]

    def _kp9_replace_before_cursor(self, count: int, text: str, skip_after: int) -> None:
        before, after = self._kp9_around_cursor()
        head = before[: len(before) - count] + text
        self.value = head + after
        self.cursor_position = len(head) + skip_after

    def _kp9_suggest_at(self) -> Offset:
        return self.cursor_screen_offset

    async def _on_key(self, event: events.Key) -> None:
        if self.completion_key(event):
            return
        await super()._on_key(event)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is self:
            self.refresh_suggestions()

    def on_blur(self, event: events.Blur) -> None:
        if self.var_box is not None:
            self.var_box.hide()


class VarTextArea(_Completion, TextArea):
    def _kp9_around_cursor(self) -> tuple[str, str]:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        return line[:col], line[col:]

    def _kp9_replace_before_cursor(self, count: int, text: str, skip_after: int) -> None:
        row, col = self.cursor_location
        start = (row, col - count)
        self.replace(text, start, (row, col))
        self.cursor_location = (row, col - count + len(text) + skip_after)

    def _kp9_suggest_at(self) -> Offset:
        return self.cursor_screen_offset

    async def _on_key(self, event: events.Key) -> None:
        if self.completion_key(event):
            return
        await super()._on_key(event)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area is self:
            self.refresh_suggestions()

    def on_blur(self, event: events.Blur) -> None:
        if self.var_box is not None:
            self.var_box.hide()
