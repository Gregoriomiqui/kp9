from kp9.tui.views.groups import CollectionsView, GroupsView
from kp9.tui.views.requests import RequestsView

SIZE = (120, 40)
COL = "groups/pagos/checkout-api"


async def test_starts_on_groups_with_topbar(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.current, GroupsView)
        assert app.current.table.row_count == 1
        assert "Workspace: mis-apis" in app.topbar_text
        assert "Env: <qa>" in app.topbar_text
        assert app.crumbs_text == "<grupos>"


async def test_enter_drills_down_and_escape_goes_back(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.current, CollectionsView)
        assert "Grupo: Pagos" in app.topbar_text
        await pilot.press("enter")
        await pilot.pause()
        view = app.current
        assert isinstance(view, RequestsView)
        assert [r.key for r in view.visible_rows()] == [
            str(sample_ws / COL / "carrito"),
            str(sample_ws / COL / "buscar.json"),
        ]
        await pilot.press("enter")
        await pilot.pause()
        assert app.crumbs_text == "<grupos> <pagos> <checkout-api> <carrito>"
        assert "Requests(pagos/checkout-api/carrito)[2]" in str(app.current.border_title)
        await pilot.press("escape")
        await pilot.pause()
        assert app.crumbs_text == "<grupos> <pagos> <checkout-api>"
        await pilot.press("escape", "escape", "escape")
        await pilot.pause()
        assert isinstance(app.current, GroupsView)
        assert len(app.stack) == 1


async def test_shortcut_2_opens_collections_of_last_group(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        assert isinstance(app.current, GroupsView)
        await pilot.press("2")
        await pilot.pause()
        assert isinstance(app.current, CollectionsView)
        assert len(app.stack) == 2


async def test_shortcut_2_without_group_stays(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("2")
        await pilot.pause()
        assert isinstance(app.current, GroupsView)


async def test_invalid_request_marked_in_table(make_app, sample_ws):
    (sample_ws / COL / "roto.json").write_text("{")
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter", "enter")
        await pilot.pause()
        names = [str(r.cells[1]) for r in app.current.visible_rows()]
        assert "⚠ roto" in names


async def test_reload_keeps_view_and_shows_new_files(make_app, sample_ws, write_file):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter", "enter")
        await pilot.pause()
        write_file(sample_ws / COL / "nuevo.json", {"name": "Nuevo", "url": "https://x"})
        app.reload_workspace()
        await pilot.pause()
        assert isinstance(app.current, RequestsView)
        assert app.current.table.row_count == 3


async def test_removed_active_env_falls_back_to_none(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        (sample_ws / "environments" / "qa.json").unlink()
        app.reload_workspace()
        await pilot.pause()
        assert app.env_name is None
        assert "Env: <sin entorno>" in app.topbar_text


async def test_set_env_protected_marks_topbar(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        assert app.set_env("prod") is True
        await pilot.pause()
        assert "PROTEGIDO" in app.topbar_text
        assert app.query_one("#topbar").has_class("protected")
        assert app.set_env("nope") is False
        assert app.env_name == "prod"


async def test_workspace_without_environments_opens(make_app, tmp_path, write_file):
    root = tmp_path / "vacio"
    write_file(root / "workspace.json", {"name": "vacio"})
    app = make_app(root=root)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert app.env_name is None
        assert app.current.table.row_count == 0
