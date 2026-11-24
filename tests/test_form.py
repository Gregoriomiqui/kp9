import pytest

from kp9.form import (
    FormError,
    body_to_text,
    build_request,
    pairs_to_text,
    text_to_body,
    text_to_pairs,
)
from kp9.model import AuthBearer, Body, Request


def test_pairs_roundtrip():
    pairs = {"Content-Type": "application/json", "X-Url": "http://a:8080/x"}
    assert pairs_to_text(pairs) == "Content-Type: application/json\nX-Url: http://a:8080/x"
    assert text_to_pairs(pairs_to_text(pairs), "headers") == pairs


def test_text_to_pairs_skips_blank_and_comment_lines():
    assert text_to_pairs("\n# nota\n a : 1 \n\nb:\n", "params") == {"a": "1", "b": ""}


def test_text_to_pairs_reports_bad_line():
    with pytest.raises(FormError, match="headers, línea 2: falta ':'"):
        text_to_pairs("a: 1\nsolo-texto", "headers")
    with pytest.raises(FormError, match="params, línea 1: falta el nombre"):
        text_to_pairs(": v", "params")


def test_body_text_conversions():
    assert body_to_text(Body()) == ""
    assert body_to_text(Body(type="json", content={"sku": "{{sku}}", "qty": 1})) == (
        '{\n  "sku": "{{sku}}",\n  "qty": 1\n}'
    )
    assert body_to_text(Body(type="text", content="<x/>")) == "<x/>"
    assert body_to_text(Body(type="form-urlencoded", content={"a": "1"})) == '{\n  "a": "1"\n}'


def test_text_to_body():
    assert text_to_body("json", '{"qty": 1}') == Body(type="json", content={"qty": 1})
    assert text_to_body("json", "  ") == Body(type="json", content=None)
    assert text_to_body("text", "hola\n") == Body(type="text", content="hola\n")
    assert text_to_body("none", "ignorado") == Body()
    assert text_to_body("multipart", '{"f": "@~/a.pdf"}') == Body(
        type="multipart", content={"f": "@~/a.pdf"}
    )


def test_text_to_body_errors():
    with pytest.raises(FormError, match=r"body, línea 2, columna 7"):
        text_to_body("json", '{"a": 1,\n "b": }')
    with pytest.raises(FormError, match="debe ser un objeto JSON"):
        text_to_body("form-urlencoded", "[1, 2]")


def test_build_request_keeps_name_description_and_auth():
    original = Request(name="R", description="d", url="u", auth=AuthBearer(token="t"))
    req = build_request(
        original,
        method="POST",
        url="  {{baseUrl}}/x ",
        params_text="q: 1",
        headers_text="",
        body_type="json",
        body_text='{"a": "{{sku}}"}',
    )
    assert (req.name, req.description, req.auth) == ("R", "d", AuthBearer(token="t"))
    assert req.method == "POST"
    assert req.url == "{{baseUrl}}/x"
    assert req.params == {"q": "1"}
    assert req.body == Body(type="json", content={"a": "{{sku}}"})
