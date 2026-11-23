import json

from typer.testing import CliRunner

from kp9 import cli
from kp9.cli import app

runner = CliRunner()

COLLECTION = {
    "info": {
        "name": "Demo",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [{"name": "Ping", "request": {"method": "GET", "url": "{{baseUrl}}/ping"}}],
}
ENV = {"name": "qa", "values": [{"key": "baseUrl", "value": "https://qa", "enabled": True}]}


def test_init_creates_workspace(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path / "w"), "--name", "mis-apis"])
    assert result.exit_code == 0, result.output
    assert json.loads((tmp_path / "w" / "workspace.json").read_text())["name"] == "mis-apis"
    assert "Workspace creado" in result.output


def test_init_default_name_is_directory_name(tmp_path):
    runner.invoke(app, ["init", str(tmp_path / "mis-apis")])
    assert json.loads((tmp_path / "mis-apis" / "workspace.json").read_text())["name"] == "mis-apis"


def test_init_twice_fails(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)])
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 1
    assert "ya existe" in result.output


def test_import_collection_and_env(tmp_path):
    ws = tmp_path / "w"
    runner.invoke(app, ["init", str(ws)])
    col = tmp_path / "col.json"
    col.write_text(json.dumps(COLLECTION))
    env = tmp_path / "env.json"
    env.write_text(json.dumps(ENV))
    result = runner.invoke(
        app, ["import", str(col), "--group", "pagos", "--env", str(env), "--workspace", str(ws)]
    )
    assert result.exit_code == 0, result.output
    assert "1 requests importados en 0 carpetas" in result.output
    assert "1 entorno(s) importado(s)" in result.output
    assert (ws / "groups" / "pagos" / "demo" / "ping.json").exists()
    assert (ws / "environments" / "qa.json").exists()


def test_import_invalid_json_reports_location(tmp_path):
    ws = tmp_path / "w"
    runner.invoke(app, ["init", str(ws)])
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    result = runner.invoke(app, ["import", str(bad), "--group", "g", "--workspace", str(ws)])
    assert result.exit_code == 1
    assert "bad.json:1:2" in result.output


def test_import_non_postman_file_fails(tmp_path):
    ws = tmp_path / "w"
    runner.invoke(app, ["init", str(ws)])
    other = tmp_path / "x.json"
    other.write_text("{}")
    result = runner.invoke(app, ["import", str(other), "--group", "g", "--workspace", str(ws)])
    assert result.exit_code == 1
    assert "falta 'item'" in result.output


def test_tui_outside_workspace_uses_default_home(tmp_path, monkeypatch):
    home = tmp_path / "home-kp9"
    monkeypatch.setenv("KP9_HOME", str(home))
    monkeypatch.chdir(tmp_path)
    launched = []
    monkeypatch.setattr(cli, "_launch_tui", launched.append)
    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.output
    assert launched == [home.resolve()]
    assert json.loads((home / "workspace.json").read_text())["name"] == "kp9"
    assert "Workspace creado" in result.output
    # la segunda vez reutiliza el mismo workspace sin volver a crearlo
    result = runner.invoke(app, [])
    assert result.exit_code == 0 and "Workspace creado" not in result.output


def test_default_home_is_tilde_kp9(tmp_path, monkeypatch):
    monkeypatch.delenv("KP9_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.default_home() == tmp_path / "kp9"


def test_explicit_workspace_not_found_still_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("KP9_HOME", str(tmp_path / "h"))
    result = runner.invoke(app, ["--workspace", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "kp9 init" in result.output


def test_tui_launches_with_found_root(sample_ws, monkeypatch):
    launched = []
    monkeypatch.setattr(cli, "_launch_tui", launched.append)
    result = runner.invoke(app, ["--workspace", str(sample_ws / "groups")])
    assert result.exit_code == 0, result.output
    assert launched == [sample_ws]
