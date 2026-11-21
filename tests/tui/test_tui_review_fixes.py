"""Regresiones de la revisión final (TUI)."""

import json

import httpx

from kp9.httpclient import Response
from kp9.tui.views.detail import DetailView
from kp9.tui.views.groups import CollectionsView
from kp9.tui.widgets import ResponsePanel

SIZE = (120, 40)


async def test_response_panel_strips_control_sequences(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        panel = app.query_one(ResponsePanel) if app.query(ResponsePanel) else None
        if panel is None:
            panel = ResponsePanel()
            await app.mount(panel)
        resp = Response(
            200,
            "OK",
            [("content-type", "text/plain"), ("x-evil", "a\x1b[31mb")],
            b"\x1b[31mRED\x1b[0m \x1b]52;c;ZXZpbA==\x1b\\ \x9b ok\n\tfin",
            1.0,
        )
        panel.show_response(resp)
        await pilot.pause()
        assert "\x1b" not in panel.body_text
        assert "\x9b" not in panel.body_text
        assert "\x1b" not in panel.headers_text
        assert "\n\tfin" in panel.body_text


async def test_markup_in_descriptions_does_not_crash(make_app, sample_ws):
    group = sample_ws / "groups/pagos/group.json"
    data = json.loads(group.read_text())
    data["description"] = "Legacy [/] api [docs](https://x.io)"
    group.write_text(json.dumps(data))
    col = sample_ws / "groups/pagos/checkout-api/collection.json"
    cdata = json.loads(col.read_text())
    cdata["description"] = "[/] [b]x"
    col.write_text(json.dumps(cdata))
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_view(CollectionsView(sample_ws / "groups/pagos"))
        await pilot.pause()
        assert isinstance(app.current, CollectionsView)


async def test_notify_with_markup_chars_does_not_crash(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        app.notify("comando desconocido: [/x] [Admin]")
        await pilot.pause()
        app.run_command("nope[/x]")
        await pilot.pause()
        assert app.is_running


async def test_send_with_unexpected_error_does_not_crash(make_app, sample_ws):
    def boom(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("explotó")

    app = make_app(handler=boom)
    async with app.run_test(size=SIZE) as pilot:
        app.push_view(DetailView(sample_ws / "groups/pagos/checkout-api/carrito/ver-carrito.json"))
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.is_running
        assert "explotó" in app.current.panel.error_text
        assert app.history.list()[0].error is not None


async def test_import_non_utf8_file_does_not_crash(make_app, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe{")
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        app.import_file(str(bad))
        await pilot.pause()
        assert app.is_running
