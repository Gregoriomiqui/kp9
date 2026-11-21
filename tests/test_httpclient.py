import json

import httpx
import pytest
import respx

from kp9.httpclient import RequestFailed, Response, full_url, send, to_curl
from kp9.model import AuthNone, Body
from kp9.resolve import ResolvedRequest

URL = "https://api.test/items"


def rr(**kw):
    base = dict(method="GET", url=URL, params={}, headers={}, body=Body(), auth=AuthNone())
    base.update(kw)
    return ResolvedRequest(**base)


@respx.mock
async def test_send_json_body_and_response():
    route = respx.post(URL).mock(
        return_value=httpx.Response(201, json={"id": 7}, headers={"X-Req": "1"})
    )
    async with httpx.AsyncClient() as client:
        resp = await send(
            rr(
                method="POST",
                params={"channel": "web"},
                body=Body(type="json", content={"sku": "A"}),
            ),
            client,
            timeout=5,
        )
    sent = route.calls.last.request
    assert sent.url.params["channel"] == "web"
    assert json.loads(sent.content) == {"sku": "A"}
    assert sent.headers["content-type"] == "application/json"
    assert (resp.status, resp.reason) == (201, "Created")
    assert ("x-req", "1") in resp.headers
    assert resp.elapsed_ms >= 0
    assert json.loads(resp.text()) == {"id": 7}


@respx.mock
async def test_send_text_and_form_bodies():
    route = respx.post(URL).mock(return_value=httpx.Response(200))
    async with httpx.AsyncClient() as client:
        await send(rr(method="POST", body=Body(type="text", content="hola {x}")), client, 5)
        assert route.calls.last.request.content == b"hola {x}"
        await send(
            rr(method="POST", body=Body(type="form-urlencoded", content={"a": "1", "b": 2})),
            client,
            5,
        )
    sent = route.calls.last.request
    assert sent.content == b"a=1&b=2"
    assert sent.headers["content-type"] == "application/x-www-form-urlencoded"


@respx.mock
async def test_send_multipart_with_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("contenido")
    route = respx.post(URL).mock(return_value=httpx.Response(200))
    async with httpx.AsyncClient() as client:
        await send(
            rr(
                method="POST",
                body=Body(type="multipart", content={"desc": "foto", "file": f"@{f}"}),
            ),
            client,
            5,
        )
    sent = route.calls.last.request
    assert sent.headers["content-type"].startswith("multipart/form-data")
    assert b'filename="f.txt"' in sent.content
    assert b"contenido" in sent.content
    assert b"foto" in sent.content


async def test_multipart_missing_file_is_body_error(tmp_path):
    async with httpx.AsyncClient() as client:
        with pytest.raises(RequestFailed) as exc:
            await send(
                rr(
                    method="POST", body=Body(type="multipart", content={"f": f"@{tmp_path}/no.txt"})
                ),
                client,
                5,
            )
    assert exc.value.kind == "body"


async def test_form_body_must_be_object():
    async with httpx.AsyncClient() as client:
        with pytest.raises(RequestFailed) as exc:
            await send(
                rr(method="POST", body=Body(type="form-urlencoded", content="a=1")), client, 5
            )
    assert exc.value.kind == "body"


@respx.mock
async def test_timeout_maps_to_request_failed():
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout)
    async with httpx.AsyncClient() as client:
        with pytest.raises(RequestFailed) as exc:
            await send(rr(), client, timeout=5)
    assert exc.value.kind == "timeout"
    assert str(exc.value) == "timeout tras 5 s"


@respx.mock
async def test_connect_error_and_tls_error():
    respx.get(URL).mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(RequestFailed) as exc:
            await send(rr(), client, 5)
    assert exc.value.kind == "network"

    respx.get(URL).mock(
        side_effect=httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(RequestFailed) as exc:
            await send(rr(), client, 5)
    assert exc.value.kind == "tls"


def resp(body: bytes, content_type: str | None = None) -> Response:
    headers = [("content-type", content_type)] if content_type else []
    return Response(status=200, reason="OK", headers=headers, body=body, elapsed_ms=1.0)


def test_text_uses_declared_charset():
    assert resp("ñ".encode("latin-1"), "text/plain; charset=latin-1").text() == "ñ"


def test_unknown_charset_falls_back_to_utf8():
    assert resp("ñ".encode(), "text/plain; charset=nope").text() == "ñ"


def test_invalid_utf8_does_not_raise():
    assert "�" in resp(b"\xff\xfeabc").text()


def test_binary_detection_and_placeholder():
    png = resp(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image/png")
    assert png.is_binary
    assert png.pretty() == "‹contenido binario, 16 bytes›"
    assert not resp(b"\x00", "application/json").is_binary


def test_pretty_json_keeps_unicode():
    r = resp('{"a":"ñ","b":[1]}'.encode(), "application/json")
    assert r.is_json
    assert r.pretty() == '{\n  "a": "ñ",\n  "b": [\n    1\n  ]\n}'


def test_pretty_non_json_returns_text():
    assert resp(b"<html/>", "text/html").pretty() == "<html/>"


def test_full_url_merges_params():
    assert full_url(rr(url="https://a/x?z=1", params={"q": "a b"})) == "https://a/x?z=1&q=a+b"
    assert full_url(rr(url="https://a/x")) == "https://a/x"


def test_to_curl_json():
    curl = to_curl(
        rr(method="POST", params={"channel": "web"}, body=Body(type="json", content={"sku": "A"}))
    )
    assert curl == (
        "curl -X POST 'https://api.test/items?channel=web' "
        "-H 'Content-Type: application/json' --data-raw '{\"sku\": \"A\"}'"
    )


def test_to_curl_simple_get_and_form():
    assert to_curl(rr()) == "curl -X GET https://api.test/items"
    form = to_curl(rr(method="POST", body=Body(type="form-urlencoded", content={"a": "1 2"})))
    assert form == "curl -X POST https://api.test/items --data-urlencode 'a=1 2'"
