import json

from watchfiles import Change

from kp9.tui import editor
from kp9.tui.app import _relevant_change
from kp9.tui.widgets import ConfirmScreen

SIZE = (120, 40)
COL = "groups/pagos/checkout-api"


async def goto_col(app, pilot, type_keys):
    await pilot.press("colon")
    await type_keys(pilot, "col checkout-api")
    await pilot.press("enter")
    await pilot.pause()


def fake_editor(monkeypatch, write=None):
    calls = []

    def _open(app, path):
        calls.append(path)
        if write is not None:
            write(path)

    monkeypatch.setattr(editor, "open_in_editor", _open)
    return calls


async def test_edit_request_reloads(make_app, sample_ws, monkeypatch, type_keys):
    def rename(path):
        data = json.loads(path.read_text())
        data["name"] = "Buscar v2"
        path.write_text(json.dumps(data))

    calls = fake_editor(monkeypatch, rename)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        await pilot.press("down", "e")
        await pilot.pause()
        assert calls == [sample_ws / COL / "buscar.json"]
        assert str(app.current.visible_rows()[1].cells[1]) == "Buscar v2"


async def test_edit_invalid_offers_reopen(make_app, sample_ws, monkeypatch, type_keys):
    calls = fake_editor(monkeypatch, lambda path: path.write_text("{"))
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        await pilot.press("down", "e")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause()
        assert len(calls) == 2
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)


async def test_edit_folder_creates_folder_json(make_app, sample_ws, monkeypatch, type_keys):
    calls = fake_editor(monkeypatch)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        await pilot.press("e")
        await pilot.pause()
        folder_json = sample_ws / COL / "carrito" / "folder.json"
        assert calls == [folder_json]
        assert json.loads(folder_json.read_text())["name"] == "carrito"


async def test_new_request_creates_file_and_opens_editor(
    make_app, sample_ws, monkeypatch, type_keys
):
    calls = fake_editor(monkeypatch)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        await pilot.press("n")
        await pilot.pause()
        await type_keys(pilot, "nuevo")
        await pilot.press("enter")
        await pilot.pause()
        created = sample_ws / COL / "nuevo.json"
        assert json.loads(created.read_text())["url"] == "{{baseUrl}}/"
        assert calls == [created]
        assert app.current.table.row_count == 3


async def test_new_folder_with_trailing_slash(make_app, sample_ws, monkeypatch, type_keys):
    calls = fake_editor(monkeypatch)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        await pilot.press("n")
        await pilot.pause()
        await type_keys(pilot, "sub/")
        await pilot.press("enter")
        await pilot.pause()
        assert (sample_ws / COL / "sub" / "folder.json").exists()
        assert calls == []


async def test_new_name_cancelled_with_escape(make_app, sample_ws, monkeypatch, type_keys):
    fake_editor(monkeypatch)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.current.table.row_count == 2


async def test_delete_request_with_confirmation(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        await pilot.press("down", "d")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n")
        await pilot.pause()
        assert (sample_ws / COL / "buscar.json").exists()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert not (sample_ws / COL / "buscar.json").exists()
        assert app.current.table.row_count == 1


async def test_new_environment_from_envs_view(make_app, sample_ws, monkeypatch, type_keys):
    calls = fake_editor(monkeypatch)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        await type_keys(pilot, "staging")
        await pilot.press("enter")
        await pilot.pause()
        assert calls == [sample_ws / "environments" / "staging.json"]
        assert "staging" in app.workspace.environments


async def test_new_group(make_app, sample_ws, monkeypatch, type_keys):
    fake_editor(monkeypatch)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("n")
        await pilot.pause()
        await type_keys(pilot, "catalogo")
        await pilot.press("enter")
        await pilot.pause()
        assert (sample_ws / "groups" / "catalogo" / "group.json").exists()
        assert app.current.table.row_count == 2


async def test_edit_from_detail_view(make_app, sample_ws, monkeypatch, type_keys):
    calls = fake_editor(monkeypatch)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        await pilot.press("down", "enter")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert calls == [sample_ws / COL / "buscar.json"]


async def test_import_command_into_current_group(make_app, sample_ws, tmp_path, type_keys):
    postman = tmp_path / "demo.json"
    postman.write_text(
        json.dumps(
            {
                "info": {
                    "name": "Demo",
                    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                },
                "item": [{"name": "Ping", "request": {"method": "GET", "url": "{{baseUrl}}/ping"}}],
            }
        )
    )
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await goto_col(app, pilot, type_keys)
        app.run_command(f"import {postman}")
        await pilot.pause()
        assert (sample_ws / "groups" / "pagos" / "demo" / "ping.json").exists()
        app.run_command(f"import {tmp_path / 'no-existe.json'}")
        await pilot.pause()
        app.run_command("import")
        await pilot.pause()


async def test_import_environment_command(make_app, sample_ws, tmp_path):
    env = tmp_path / "stg.json"
    env.write_text(
        json.dumps({"name": "stg", "values": [{"key": "baseUrl", "value": "https://s"}]})
    )
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        app.run_command(f"import {env}")
        await pilot.pause()
        assert "stg" in app.workspace.environments


def test_relevant_change_filter():
    assert _relevant_change(Change.modified, "/w/groups/a/b.json") is True
    assert _relevant_change(Change.modified, "/w/.kp9/history.db") is False
    assert _relevant_change(Change.added, "/w/.git/index") is False


def test_editor_command(monkeypatch):
    monkeypatch.setenv("EDITOR", "code --wait")
    assert editor.editor_command() == ["code", "--wait"]
    monkeypatch.delenv("EDITOR")
    assert editor.editor_command() == ["vi"]
