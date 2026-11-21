import json

import pytest

from kp9.importer.postman import (
    PostmanImportError,
    format_report,
    import_collection,
    import_environment,
    is_environment,
)
from kp9.secrets import load_secrets
from kp9.store import init_workspace, load_workspace

POSTMAN = {
    "info": {
        "name": "Checkout API",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        "description": "API de checkout",
    },
    "auth": {
        "type": "bearer",
        "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}],
    },
    "variable": [
        {"key": "apiVersion", "value": "v1"},
        {"key": "off", "value": "x", "disabled": True},
    ],
    "event": [{"listen": "prerequest", "script": {"exec": ["console.log(1)"]}}],
    "item": [
        {
            "name": "Carrito",
            "auth": {
                "type": "apikey",
                "apikey": [
                    {"key": "key", "value": "X-Api-Key"},
                    {"key": "value", "value": "{{apiKey}}"},
                    {"key": "in", "value": "header"},
                ],
            },
            "item": [
                {
                    "name": "Agregar al carrito",
                    "event": [{"listen": "test", "script": {"exec": ["pm.test('ok')"]}}],
                    "request": {
                        "method": "POST",
                        "header": [
                            {"key": "Content-Type", "value": "application/json"},
                            {"key": "X-Off", "value": "1", "disabled": True},
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": '{"sku": "{{sku}}", "qty": 1}',
                            "options": {"raw": {"language": "json"}},
                        },
                        "url": {
                            "raw": "{{baseUrl}}/v1/cart/items?channel=web&debug=1",
                            "query": [
                                {"key": "channel", "value": "web"},
                                {"key": "debug", "value": "1", "disabled": True},
                            ],
                        },
                    },
                },
                {
                    "name": "Agregar al carrito",
                    "request": {"method": "POST", "url": "{{baseUrl}}/v2/cart/items"},
                },
                {"name": "Folder", "request": {"method": "GET", "url": "{{baseUrl}}/folder"}},
            ],
        },
        {
            "name": "Login",
            "request": {
                "method": "POST",
                "url": "{{authUrl}}/login",
                "body": {
                    "mode": "urlencoded",
                    "urlencoded": [{"key": "user", "value": "{{user}}"}],
                },
                "auth": {
                    "type": "basic",
                    "basic": [
                        {"key": "username", "value": "{{user}}"},
                        {"key": "password", "value": "{{pass}}"},
                    ],
                },
            },
        },
        {
            "name": "Subir",
            "request": {
                "method": "POST",
                "url": "{{baseUrl}}/upload",
                "body": {
                    "mode": "formdata",
                    "formdata": [
                        {"key": "desc", "value": "foto", "type": "text"},
                        {"key": "file", "type": "file", "src": "/tmp/foto.png"},
                    ],
                },
            },
        },
        {
            "name": "Token",
            "request": {
                "method": "GET",
                "url": "{{baseUrl}}/me",
                "auth": {
                    "type": "oauth2",
                    "oauth2": [
                        {"key": "grant_type", "value": "client_credentials"},
                        {"key": "accessTokenUrl", "value": "{{authUrl}}/token"},
                        {"key": "clientId", "value": "{{cid}}"},
                        {"key": "clientSecret", "value": "{{csecret}}"},
                        {"key": "scope", "value": "read write"},
                    ],
                },
            },
        },
        {
            "name": "Hawk",
            "request": {
                "method": "GET",
                "url": "{{baseUrl}}/hawk",
                "auth": {"type": "hawk", "hawk": []},
            },
        },
        {
            "name": "Raw con var",
            "request": {
                "method": "POST",
                "url": "{{baseUrl}}/raw",
                "body": {
                    "mode": "raw",
                    "raw": '{"qty": {{qty}}}',
                    "options": {"raw": {"language": "json"}},
                },
            },
        },
    ],
}


@pytest.fixture
def root(tmp_path):
    return init_workspace(tmp_path / "w", "w")


def read(path):
    return json.loads(path.read_text())


def test_import_counts_and_structure(root):
    report = import_collection(POSTMAN, root, "pagos")
    col = root / "groups" / "pagos" / "checkout-api"
    assert report.target == col
    assert (report.requests, report.folders) == (8, 1)
    assert read(root / "groups/pagos/group.json")["name"] == "pagos"
    meta = read(col / "collection.json")
    assert meta["name"] == "Checkout API"
    assert meta["description"] == "API de checkout"
    assert meta["auth"] == {"type": "bearer", "token": "{{token}}"}
    assert meta["variables"] == {"apiVersion": "v1"}
    folder = read(col / "carrito" / "folder.json")
    assert folder["name"] == "Carrito"
    assert folder["auth"] == {
        "type": "apikey",
        "key": "X-Api-Key",
        "value": "{{apiKey}}",
        "in": "header",
    }


def test_import_request_details(root):
    import_collection(POSTMAN, root, "pagos")
    col = root / "groups" / "pagos" / "checkout-api"
    agregar = read(col / "carrito" / "agregar-al-carrito.json")
    assert agregar["url"] == "{{baseUrl}}/v1/cart/items"
    assert agregar["params"] == {"channel": "web"}
    assert agregar["headers"] == {"Content-Type": "application/json"}
    assert agregar["body"] == {"type": "json", "content": {"sku": "{{sku}}", "qty": 1}}
    assert agregar["auth"] == {"type": "inherit"}
    login = read(col / "login.json")
    assert login["body"] == {"type": "form-urlencoded", "content": {"user": "{{user}}"}}
    assert login["auth"] == {"type": "basic", "username": "{{user}}", "password": "{{pass}}"}
    subir = read(col / "subir.json")
    assert subir["body"] == {
        "type": "multipart",
        "content": {"desc": "foto", "file": "@/tmp/foto.png"},
    }
    token = read(col / "token.json")
    assert token["auth"] == {
        "type": "oauth2-cc",
        "tokenUrl": "{{authUrl}}/token",
        "clientId": "{{cid}}",
        "clientSecret": "{{csecret}}",
        "scopes": ["read", "write"],
    }
    raw = read(col / "raw-con-var.json")
    assert raw["body"] == {"type": "text", "content": '{"qty": {{qty}}}'}
    assert raw["headers"] == {"Content-Type": "application/json"}


def test_duplicate_and_reserved_names_never_overwrite(root):
    import_collection(POSTMAN, root, "pagos")
    carrito = root / "groups" / "pagos" / "checkout-api" / "carrito"
    assert read(carrito / "agregar-al-carrito-2.json")["url"] == "{{baseUrl}}/v2/cart/items"
    assert read(carrito / "folder-2.json")["name"] == "Folder"
    assert read(carrito / "folder.json")["name"] == "Carrito"


def test_skipped_items_are_reported(root):
    skipped = import_collection(POSTMAN, root, "pagos").skipped
    assert "Checkout API: script 'prerequest' omitido" in skipped
    assert "Checkout API/Carrito/Agregar al carrito: script 'test' omitido" in skipped
    assert "Checkout API/Hawk: auth 'hawk' no soportada" in skipped
    assert any(s.startswith("Checkout API/Raw con var: body JSON inválido") for s in skipped)


def test_imported_workspace_loads_cleanly(root):
    import_collection(POSTMAN, root, "pagos")
    ws = load_workspace(root)
    assert ws.errors == []
    [group] = ws.groups
    [col] = group.children
    assert col.name == "Checkout API"


def test_importing_twice_creates_new_collection_dir(root):
    import_collection(POSTMAN, root, "pagos")
    second = import_collection(POSTMAN, root, "pagos")
    assert second.target == root / "groups" / "pagos" / "checkout-api-2"


def test_not_a_collection_raises(root):
    with pytest.raises(PostmanImportError, match="falta 'item'"):
        import_collection({"info": {}}, root, "pagos")
    with pytest.raises(PostmanImportError, match="no soportada"):
        import_collection({"info": {"schema": "v1.0"}, "item": []}, root, "pagos")


ENV = {
    "name": "QA",
    "values": [
        {"key": "baseUrl", "value": "https://qa", "enabled": True},
        {"key": "token", "value": "tok", "type": "secret", "enabled": True},
        {"key": "off", "value": "1", "enabled": False},
    ],
}


def test_import_environment_splits_secrets(root):
    assert is_environment(ENV)
    assert not is_environment(POSTMAN)
    report = import_environment(ENV, root)
    path = root / "environments" / "qa.json"
    assert report.target == path
    assert report.environments == 1
    assert read(path) == {
        "name": "QA",
        "description": "",
        "protected": False,
        "variables": {"baseUrl": "https://qa", "token": {"secret": True}},
    }
    assert load_secrets(root) == {"QA": {"token": "tok"}}
    with pytest.raises(PostmanImportError, match="ya existe"):
        import_environment(ENV, root)


def test_import_environment_rejects_other_files(root):
    with pytest.raises(PostmanImportError, match="falta 'values'"):
        import_environment(POSTMAN, root)


def test_format_report(root):
    text = format_report(import_collection(POSTMAN, root, "pagos"))
    assert "8 requests importados en 1 carpetas" in text
    assert "  - Checkout API/Hawk: auth 'hawk' no soportada" in text
