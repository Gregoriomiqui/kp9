"""Regresiones de la revisión final (núcleo)."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from kp9.history import History
from kp9.httpclient import RequestFailed, Response, send
from kp9.importer.postman import PostmanImportError, import_collection, import_environment
from kp9.model import AuthNone, Body, Environment, SecretRef
from kp9.redact import MASK, Redactor
from kp9.resolve import ResolvedRequest
from kp9.secrets import env_values, load_secrets


def _req(**kw):
    base = dict(
        method="GET", url="https://x.test/a", params={}, headers={}, body=Body(), auth=AuthNone()
    )
    base.update(kw)
    return ResolvedRequest(**base)


def _resp(body: bytes, ctype: str) -> Response:
    return Response(200, "OK", [("content-type", ctype)], body, 1.0)


# ---- binarios -----------------------------------------------------------


@pytest.mark.parametrize(
    "ctype", ["application/octet-stream", "application/pdf", "image/png", "application/zip"]
)
def test_binary_content_types_are_binary_without_nul(ctype):
    assert _resp(b"%PDF-1.7 \xe2\x80 abc", ctype).is_binary


def test_undecodable_unknown_type_is_binary():
    assert _resp(b"\xff\xfe\xfa\xfb" * 10, "").is_binary


def test_text_type_with_bad_bytes_is_not_binary():
    assert not _resp(b"caf\xe9", "text/plain; charset=utf-8").is_binary


# ---- headers no ASCII ---------------------------------------------------


@respx.mock
async def test_non_ascii_header_is_sent_as_utf8():
    route = respx.get("https://x.test/a").mock(return_value=httpx.Response(200))
    async with httpx.AsyncClient() as client:
        await send(_req(headers={"X-User": "José"}), client, 5)
    assert route.calls[0].request.headers.raw[-1][1] == "José".encode()


@respx.mock
async def test_invalid_header_name_raises_request_failed():
    respx.get("https://x.test/a").mock(return_value=httpx.Response(200))
    async with httpx.AsyncClient() as client:
        with pytest.raises(RequestFailed):
            await send(_req(headers={"X Ñ": "v"}), client, 5)


# ---- historial ------------------------------------------------------------


def test_history_keeps_undecodable_bytes_and_redacts_binary(tmp_path):
    history = History(tmp_path / "h.db")
    red = Redactor(["s3cr3t"])
    raw = b"\x89PNG s3cr3t \xff\xfe"
    hid = history.record(
        req=_req(),
        response=_resp(raw, "image/png"),
        error=None,
        redactor=red,
        env=None,
        request_path=None,
    )
    stored = history.get(hid).response_body
    assert b"s3cr3t" not in stored
    assert stored == raw.replace(b"s3cr3t", MASK.encode())
    text_raw = b"caf\xe9 s3cr3t"
    hid = history.record(
        req=_req(),
        response=_resp(text_raw, "text/plain; charset=utf-8"),
        error=None,
        redactor=red,
        env=None,
        request_path=None,
    )
    assert history.get(hid).response_body == text_raw.replace(b"s3cr3t", MASK.encode())


# ---- secretos transformados --------------------------------------------------


def test_redactor_masks_json_escaped_variants():
    red = Redactor(['pa"ss/wörd'])
    echoed = json.dumps({"p": 'pa"ss/wörd'})  # ensure_ascii → ö
    assert 'pa\\"ss' not in red.text(echoed)
    assert 'pa\\"ss/w\\u00f6rd' not in red.text(echoed)
    assert red.text('{"p": "pa\\"ss\\/wörd"}') == '{"p": "' + MASK + '"}'


async def test_runner_redacts_auth_values_echoed_by_server(sample_ws, recorder):
    from kp9.runner import Runner
    from kp9.store import load_workspace

    def echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"headers": dict(request.headers)})

    ws = load_workspace(sample_ws)
    (sample_ws / "groups/pagos/group.json").write_text(
        json.dumps(
            {"name": "Pagos", "auth": {"type": "basic", "username": "u", "password": "{{token}}"}}
        )
    )
    ws = load_workspace(sample_ws)
    history = History(sample_ws / ".kp9" / "history.db")
    async with httpx.AsyncClient(transport=httpx.MockTransport(echo)) as client:
        runner = Runner(ws, history, client, environ={})
        node = ws.node_at(sample_ws / "groups/pagos/checkout-api/carrito/ver-carrito.json")
        resolved = runner.prepare(node, "qa")
        outcome = await runner.execute(resolved, "qa", node.path)
    body = history.get(outcome.history_id).response_body.decode()
    import base64

    assert base64.b64encode(b"u:qa-secret-token").decode() not in body
    assert MASK in body


# ---- secretos vacíos --------------------------------------------------------


def test_empty_secret_and_env_are_undefined(tmp_path):
    (tmp_path / ".kp9").mkdir()
    (tmp_path / ".kp9" / "secrets.json").write_text(
        json.dumps({"qa": {"token": "", "other": None}})
    )
    secrets = load_secrets(tmp_path)
    env = Environment(
        name="qa",
        variables={
            "token": SecretRef(secret=True),
            "other": SecretRef(secret=True),
            "e": "$ENV:EMPTY",
        },
    )
    assert env_values(env, secrets, {"EMPTY": ""}) == {}


# ---- importación robusta ----------------------------------------------------


def test_malformed_collection_raises_import_error(tmp_path: Path):
    with pytest.raises(PostmanImportError):
        import_collection({"info": "x", "item": []}, tmp_path, "g")


@pytest.mark.parametrize(
    "items", [[{"name": "r", "request": 5}], ["nope"], [{"name": "r", "request": {"url": 7}}]]
)
def test_malformed_items_never_crash(tmp_path: Path, items):
    try:
        import_collection({"info": {"name": "c"}, "item": items}, tmp_path, "g")
    except PostmanImportError:
        pass


def test_broken_secrets_file_raises_import_error(tmp_path: Path):
    (tmp_path / ".kp9").mkdir()
    (tmp_path / ".kp9" / "secrets.json").write_text("{nope")
    data = {"name": "qa", "values": [{"key": "t", "value": "v", "type": "secret"}]}
    with pytest.raises(PostmanImportError):
        import_environment(data, tmp_path)
