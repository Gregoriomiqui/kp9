from kp9.tui.views.detail import DetailView
from kp9.tui.views.envs import EnvsView
from kp9.tui.views.history import HistoryDetailView, HistoryView
from kp9.tui.views.requests import RequestsView
from kp9.tui.widgets import HelpScreen

SIZE = (120, 40)
VER = "groups/pagos/checkout-api/carrito/ver-carrito.json"


async def run(pilot, type_keys, command):
    await pilot.press("colon")
    await type_keys(pilot, command)
    await pilot.press("enter")
    await pilot.pause()


async def send_ver(app, pilot, sample_ws):
    app.push_view(DetailView(sample_ws / VER))
    await pilot.pause()
    await pilot.press("s")
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_envs_view_activates_and_masks(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("E")
        await pilot.pause()
        view = app.current
        assert isinstance(view, EnvsView)
        assert [r.key for r in view.visible_rows()] == ["prod", "qa"]
        assert "token = ••••" in view.vars_text
        assert "prod-secret-token" not in view.vars_text
        await pilot.press("enter")
        await pilot.pause()
        assert app.env_name == "prod"
        assert app.query_one("#topbar").has_class("protected")
        assert str(view.visible_rows()[0].cells[0]) == "●"


async def test_command_env_switches(make_app, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await run(pilot, type_keys, "env prod")
        assert app.env_name == "prod"
        await run(pilot, type_keys, "env nope")
        assert app.env_name == "prod"


async def test_command_col_jumps(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await run(pilot, type_keys, "col checkout-api")
        assert isinstance(app.current, RequestsView)
        assert app.current.container_path == sample_ws / "groups/pagos/checkout-api"
        assert app.crumbs_text == "<grupos> <pagos> <checkout-api>"
        await run(pilot, type_keys, "1")  # comando desconocido: no cambia de vista
        assert isinstance(app.current, RequestsView)


async def test_command_col_by_display_name(make_app, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await run(pilot, type_keys, "col checkout api")
        assert isinstance(app.current, RequestsView)


async def test_command_history_groups_and_quit(make_app, type_keys, monkeypatch):
    app = make_app()
    exited = []
    async with app.run_test(size=SIZE) as pilot:
        await run(pilot, type_keys, "history")
        assert isinstance(app.current, HistoryView)
        await run(pilot, type_keys, "groups")
        assert len(app.stack) == 1
        monkeypatch.setattr(app, "exit", lambda *a, **k: exited.append(True))
        await run(pilot, type_keys, "q")
        monkeypatch.undo()  # restaurar exit() antes de que run_test cierre la app
        assert exited == [True]


async def test_filter_live_and_escape(make_app, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await run(pilot, type_keys, "col checkout-api")
        await pilot.press("slash")
        await type_keys(pilot, "bus")
        view = app.current
        assert view.table.row_count == 1
        assert "</bus>" in str(view.border_title)
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query_one("#prompt").display
        assert view.table.row_count == 1
        await pilot.press("escape")
        await pilot.pause()
        assert view.table.row_count == 2
        assert app.current is view


async def test_filter_in_detail_searches_body(make_app, sample_ws, type_keys):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await send_ver(app, pilot, sample_ws)
        await pilot.press("slash")
        await type_keys(pilot, "items")
        assert app.current.panel.body_text == '  "items": ['


async def test_history_view_and_rerun(make_app, sample_ws, recorder):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await send_ver(app, pilot, sample_ws)
        await pilot.press("h")
        await pilot.pause()
        assert isinstance(app.current, HistoryView)
        assert app.current.table.row_count == 1
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.current, HistoryDetailView)
        assert app.current.panel.status_text.startswith("200 OK")
        assert "qa-secret-token" not in app.current.request_text
        await pilot.press("r")
        await pilot.pause()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.current, DetailView)
        assert len(recorder.requests) == 2
        assert len(app.history.list()) == 2


async def test_rerun_missing_file_notifies(make_app, sample_ws):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await send_ver(app, pilot, sample_ws)
        (sample_ws / VER).unlink()
        app.reload_workspace()
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.current, HistoryView)


async def test_help_screen(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
