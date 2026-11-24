import json

from kp9.tui.views.detail import DetailView
from kp9.tui.views.tree import TreeView

SIZE = (120, 40)
COL = "groups/pagos/checkout-api"

FULL = [
    "Pagos",
    "  Checkout API",
    "    carrito",
    "      POST Agregar al carrito",
    "      GET  Ver carrito",
    "    GET  Buscar",
]


async def open_tree(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    view = app.current
    assert isinstance(view, TreeView)
    return view


async def test_t_opens_tree_with_full_hierarchy(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        assert view.visible_lines() == FULL
        assert app.crumbs_text == "<grupos> <árbol>"


async def test_tree_command(make_app, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await type_keys(pilot, ":tree")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.current, TreeView)


async def test_enter_on_request_opens_detail_and_esc_returns(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        view.move_cursor_to(sample_ws / COL / "carrito" / "ver-carrito.json")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.current, DetailView)
        assert app.current.request_path == sample_ws / COL / "carrito" / "ver-carrito.json"
        await pilot.press("escape")
        await pilot.pause()
        assert app.current is view
        assert view.cursor_path() == sample_ws / COL / "carrito" / "ver-carrito.json"


async def test_enter_and_arrows_fold_containers(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        view.move_cursor_to(sample_ws / COL / "carrito")
        await pilot.press("enter")
        await pilot.pause()
        assert "      GET  Ver carrito" not in view.visible_lines()
        await pilot.press("right")
        await pilot.pause()
        assert "      GET  Ver carrito" in view.visible_lines()
        await pilot.press("left")
        await pilot.pause()
        assert "      GET  Ver carrito" not in view.visible_lines()
        # izquierda sobre un nodo plegado sube al padre
        await pilot.press("left")
        await pilot.pause()
        assert view.cursor_path() == sample_ws / COL


async def test_filter_keeps_matches_and_their_ancestors(make_app, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        await type_keys(pilot, "/ver")
        assert view.visible_lines() == [
            "Pagos",
            "  Checkout API",
            "    carrito",
            "      GET  Ver carrito",
        ]
        await pilot.press("enter")  # cierra el prompt
        await pilot.press("escape")  # quita el filtro
        await pilot.pause()
        assert view.visible_lines() == FULL


async def test_reload_keeps_folded_state_and_shows_new_files(make_app, sample_ws, write_file):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        view.move_cursor_to(sample_ws / COL / "carrito")
        await pilot.press("space")
        await pilot.pause()
        write_file(
            sample_ws / COL / "nuevo.json", {"name": "Nuevo", "method": "DELETE", "url": "u"}
        )
        app.reload_workspace()
        await pilot.pause()
        lines = view.visible_lines()
        assert "      GET  Ver carrito" not in lines
        assert "    DELETE Nuevo" in lines
        assert view.cursor_path() == sample_ws / COL / "carrito"


async def test_names_with_markup_and_invalid_files(make_app, sample_ws):
    (sample_ws / COL / "roto.json").write_text("{")
    data = json.loads((sample_ws / COL / "collection.json").read_text())
    data["name"] = "API [/] [b]v2"
    (sample_ws / COL / "collection.json").write_text(json.dumps(data))
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        lines = view.visible_lines()
        assert "  API [/] [b]v2" in lines
        assert any(line.strip().startswith("⚠") and "roto" in line for line in lines)


async def test_e_edits_selected_node(make_app, sample_ws, monkeypatch):
    app = make_app()
    edited = []
    monkeypatch.setattr(app, "edit_file", edited.append)
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        view.move_cursor_to(sample_ws / COL)
        await pilot.press("e")
        view.move_cursor_to(sample_ws / COL / "buscar.json")
        await pilot.press("e")
        assert edited == [sample_ws / COL / "collection.json", sample_ws / COL / "buscar.json"]
        monkeypatch.undo()


async def test_arrow_and_vim_keys_move_cursor(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        assert view.cursor_path() == sample_ws / "groups/pagos"
        await pilot.press("down", "down")
        assert view.cursor_path() == sample_ws / COL / "carrito"
        await pilot.press("j", "j")
        assert view.cursor_path() == sample_ws / COL / "carrito" / "ver-carrito.json"
        await pilot.press("k", "up")
        assert view.cursor_path() == sample_ws / COL / "carrito"


async def click_line(pilot, view, line):
    """Clic sobre la línea visible `line` del árbol (los offsets son relativos al widget)."""
    await pilot.click(view.tree_widget, offset=(8, line))
    await pilot.pause()


async def test_click_on_request_opens_detail(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        await click_line(pilot, view, FULL.index("      GET  Ver carrito"))
        assert isinstance(app.current, DetailView)
        assert app.current.request_path == sample_ws / COL / "carrito" / "ver-carrito.json"


async def test_click_on_folder_toggles_it(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        view = await open_tree(app, pilot)
        await click_line(pilot, view, FULL.index("    carrito"))
        assert view.cursor_path() == sample_ws / COL / "carrito"
        assert "      GET  Ver carrito" not in view.visible_lines()
        await click_line(pilot, view, FULL.index("    carrito"))
        assert "      GET  Ver carrito" in view.visible_lines()
