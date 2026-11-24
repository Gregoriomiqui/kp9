import json

from kp9.redact import MASK
from kp9.tui.request_editor import RequestEditorScreen
from kp9.tui.views.detail import DetailView
from kp9.tui.views.requests import RequestsView
from kp9.tui.views.tree import TreeView
from kp9.tui.widgets import ConfirmScreen

SIZE = (120, 45)
CARRITO = "groups/pagos/checkout-api/carrito"


async def open_editor(app, pilot, path):
    app.push_view(DetailView(path))
    await pilot.pause()
    await pilot.press("i")
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, RequestEditorScreen)
    return screen


async def test_i_opens_editor_with_fields(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, sample_ws / CARRITO / "agregar-al-carrito.json")
        assert ed.method_value == "POST"
        assert ed.url_input.value == "{{baseUrl}}/{{apiVersion}}/cart/items"
        assert ed.headers_area.text == "Content-Type: application/json"
        assert json.loads(ed.body_area.text) == {"sku": "{{sku}}", "qty": 1}
        assert ed.body_type_value == "json"


async def test_typing_braces_in_url_suggests_and_tab_completes(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        ed.url_input.focus()
        ed.url_input.cursor_position = len(ed.url_input.value)
        await type_keys(pilot, "/{{")
        names = ed.suggestions.names()
        assert ed.suggestions.display
        assert names[:2] == ["apiVersion", "baseUrl"] and "sku" in names and "token" in names
        await type_keys(pilot, "sk")
        assert ed.suggestions.names() == ["sku"]
        await pilot.press("tab")
        await pilot.pause()
        assert ed.url_input.value == "{{baseUrl}}/{{apiVersion}}/cart/{{sku}}"
        assert not ed.suggestions.display
        assert ed.url_input.has_focus


async def test_arrows_choose_and_enter_accepts(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        ed.url_input.focus()
        ed.url_input.value = ""
        await type_keys(pilot, "{{")
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert ed.url_input.value == "{{baseUrl}}"
        assert isinstance(app.screen, RequestEditorScreen)


async def test_escape_closes_suggestions_first(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        ed.url_input.focus()
        await type_keys(pilot, "{{")
        assert ed.suggestions.display
        await pilot.press("escape")
        await pilot.pause()
        assert not ed.suggestions.display
        assert isinstance(app.screen, RequestEditorScreen)


async def test_suggestions_show_value_source_and_mask_secrets(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        ed.url_input.focus()
        await type_keys(pilot, "{{")
        rendered = ed.suggestions.rendered_lines()
        assert any("sku" in r and "SKU-1" in r and "env qa" in r for r in rendered)
        assert any("token" in r and MASK in r for r in rendered)
        assert not any("qa-secret-token" in r for r in rendered)
        assert any("apiVersion" in r and "colección Checkout API" in r for r in rendered)


async def test_body_textarea_autocompletes(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        ed.body_type_value = "json"
        await pilot.pause()
        ed.body_area.focus()
        ed.body_area.text = ""
        await type_keys(pilot, '{"v": "{{api')
        assert ed.suggestions.names() == ["apiVersion"]
        await pilot.press("tab")
        await pilot.pause()
        assert ed.body_area.text == '{"v": "{{apiVersion}}'
        assert not ed.suggestions.display


async def test_completion_does_not_duplicate_closing_braces(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        ed.url_input.focus()
        ed.url_input.value = "{{}}/x"
        ed.url_input.cursor_position = 2
        await type_keys(pilot, "bas")
        await pilot.press("tab")
        await pilot.pause()
        assert ed.url_input.value == "{{baseUrl}}/x"


async def test_ctrl_s_saves_and_reloads(make_app, sample_ws, type_keys):
    path = sample_ws / CARRITO / "ver-carrito.json"
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, path)
        ed.method_value = "PUT"
        ed.url_input.value = "{{baseUrl}}/v2/cart"
        ed.params_area.text = "page: 2"
        ed.body_type_value = "json"
        ed.body_area.text = '{"sku": "{{sku}}"}'
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not isinstance(app.screen, RequestEditorScreen)
        saved = json.loads(path.read_text())
        assert saved["name"] == "Ver carrito"
        assert (saved["method"], saved["url"], saved["params"]) == (
            "PUT",
            "{{baseUrl}}/v2/cart",
            {"page": "2"},
        )
        assert saved["body"] == {"type": "json", "content": {"sku": "{{sku}}"}}
        assert app.current.summary_text.startswith("PUT  {{baseUrl}}/v2/cart")


async def test_invalid_body_shows_error_and_keeps_editor(make_app, sample_ws):
    path = sample_ws / CARRITO / "ver-carrito.json"
    before = path.read_text()
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, path)
        ed.body_type_value = "json"
        ed.body_area.text = '{"a": }'
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, RequestEditorScreen)
        assert "body, línea 1" in ed.error_text
        assert path.read_text() == before


async def test_escape_with_changes_asks_before_discarding(make_app, sample_ws):
    path = sample_ws / CARRITO / "ver-carrito.json"
    before = path.read_text()
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = await open_editor(app, pilot, path)
        ed.url_input.value = "otra"
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause()
        assert isinstance(app.current, DetailView)
        assert not isinstance(app.screen, (RequestEditorScreen, ConfirmScreen))
        assert path.read_text() == before


async def test_escape_without_changes_closes(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await open_editor(app, pilot, sample_ws / CARRITO / "ver-carrito.json")
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.current, DetailView)
        assert not isinstance(app.screen, RequestEditorScreen)


async def test_i_from_requests_list_and_tree(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        app.push_view(RequestsView(sample_ws / CARRITO))
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, RequestEditorScreen)
        assert app.screen.request_path == sample_ws / CARRITO / "agregar-al-carrito.json"
        app.pop_screen()
        await pilot.pause()
        app.push_view(TreeView())
        await pilot.pause()
        app.current.move_cursor_to(sample_ws / CARRITO / "ver-carrito.json")
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, RequestEditorScreen)
        assert app.screen.request_path == sample_ws / CARRITO / "ver-carrito.json"
