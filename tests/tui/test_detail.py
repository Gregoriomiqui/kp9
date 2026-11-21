import asyncio

import httpx

from kp9.tui.views.detail import DetailView
from kp9.tui.views.requests import RequestsView
from kp9.tui.widgets import ConfirmScreen

SIZE = (120, 40)
CARRITO = "groups/pagos/checkout-api/carrito"


async def open_detail(app, pilot, path):
    app.push_view(DetailView(path))
    await pilot.pause()
    return app.current


async def send_and_wait(app, pilot, key="s"):
    await pilot.press(key)
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_enter_on_request_opens_detail(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter", "enter", "enter", "enter")
        await pilot.pause()
        view = app.current
        assert isinstance(view, DetailView)
        assert view.summary_text.startswith("POST  {{baseUrl}}/{{apiVersion}}/cart/items")
        assert app.crumbs_text.endswith("<carrito> <agregar-al-carrito>")


async def test_send_shows_response_and_records_history(make_app, sample_ws, recorder):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_detail(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await send_and_wait(app, pilot)
        [sent] = recorder.requests
        assert str(sent.url) == "https://qa.example.com/v1/cart"
        assert sent.headers["authorization"] == "Bearer qa-secret-token"
        assert view.panel.status_text.startswith("200 OK")
        assert '"ok": true' in view.panel.body_text
        [entry] = app.history.list()
        assert entry.status == 200
        assert "qa-secret-token" not in entry.request_json


async def test_ctrl_r_also_sends(make_app, sample_ws, recorder):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await open_detail(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await send_and_wait(app, pilot, "ctrl+r")
        assert len(recorder.requests) == 1


async def test_last_column_shows_status_after_send(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter", "enter", "enter", "down", "enter")
        await pilot.pause()
        await send_and_wait(app, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.current, RequestsView)
        row = app.current.visible_rows()[1]
        assert str(row.cells[3]).startswith("200 · ")


async def test_missing_variable_blocks_send(make_app, sample_ws, recorder):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_detail(app, pilot, sample_ws / "groups/pagos/checkout-api/buscar.json")
        await send_and_wait(app, pilot)
        assert recorder.requests == []
        assert view.panel.error_text == "{{query}} no definida en qa"


async def test_no_environment_reports_missing(make_app, tmp_path, write_file, recorder):
    root = tmp_path / "sin-env"
    write_file(root / "workspace.json", {"name": "w"})
    write_file(root / "groups/g/group.json", {"name": "G"})
    write_file(root / "groups/g/c/collection.json", {"name": "C"})
    write_file(root / "groups/g/c/r.json", {"name": "R", "url": "{{baseUrl}}/x"})
    app = make_app(root=root)
    async with app.run_test(size=SIZE) as pilot:
        view = await open_detail(app, pilot, root.resolve() / "groups/g/c/r.json")
        await send_and_wait(app, pilot)
        assert view.panel.error_text == "{{baseUrl}} no definida (sin entorno activo)"
        assert recorder.requests == []


async def test_protected_env_requires_confirmation(make_app, sample_ws, recorder):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        app.set_env("prod")
        await open_detail(app, pilot, sample_ws / CARRITO / "agregar-al-carrito.json")
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)
        assert recorder.requests == []
        await pilot.press("s")
        await pilot.pause()
        await send_and_wait(app, pilot, "y")
        [sent] = recorder.requests
        assert str(sent.url) == "https://api.example.com/v1/cart/items"


async def test_get_on_protected_env_needs_no_confirmation(make_app, sample_ws, recorder):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        app.set_env("prod")
        await open_detail(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await send_and_wait(app, pilot)
        assert len(recorder.requests) == 1


async def test_escape_cancels_in_flight_request(make_app, sample_ws):
    async def slow(request):
        await asyncio.Event().wait()

    app = make_app(handler=slow)
    async with app.run_test(size=SIZE) as pilot:
        view = await open_detail(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await pilot.press("s")
        await pilot.pause()
        assert view.in_flight
        await pilot.press("escape")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert view.panel.error_text == "cancelado"
        assert app.current is view
        assert app.history.list()[0].error == "cancelado"


async def test_network_error_shown_and_recorded(make_app, sample_ws):
    def boom(request):
        raise httpx.ConnectError("sin red", request=request)

    app = make_app(handler=boom)
    async with app.run_test(size=SIZE) as pilot:
        view = await open_detail(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await send_and_wait(app, pilot)
        assert view.panel.error_text == "network: sin red"
        assert app.history.list()[0].status is None


async def test_invalid_request_file_shows_error(make_app, sample_ws):
    bad = sample_ws / CARRITO / "roto.json"
    bad.write_text("{")
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_detail(app, pilot, bad)
        assert view.summary_text.startswith("⚠")
        await send_and_wait(app, pilot)
        assert "roto.json:1:2" in view.panel.error_text


async def test_copy_curl_and_body(make_app, sample_ws, monkeypatch):
    app = make_app()
    copied: list[str] = []
    monkeypatch.setattr(app, "copy_to_clipboard", copied.append)
    async with app.run_test(size=SIZE) as pilot:
        await open_detail(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await send_and_wait(app, pilot, "c")
        assert copied[-1] == (
            "curl -X GET https://qa.example.com/v1/cart -H 'Authorization: Bearer qa-secret-token'"
        )
        await pilot.press("y")
        await pilot.pause()
        assert len(copied) == 1
        await send_and_wait(app, pilot)
        await pilot.press("y")
        await pilot.pause()
        assert copied[-1] == '{\n  "ok": true,\n  "items": [\n    1,\n    2\n  ]\n}'


async def test_large_body_is_truncated(make_app, sample_ws, recorder):
    recorder.responder = lambda request: httpx.Response(200, text="x" * 300_000)
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_detail(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await send_and_wait(app, pilot)
        assert len(view.panel.body_text) < 210_000
        assert "respuesta truncada" in view.panel.body_text


async def test_binary_body_placeholder(make_app, sample_ws, recorder):
    recorder.responder = lambda request: httpx.Response(
        200, content=b"\x89PNG\r\n\x1a\n\x00\x00", headers={"content-type": "image/png"}
    )
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_detail(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await send_and_wait(app, pilot)
        assert view.panel.body_text.startswith("‹contenido binario")
