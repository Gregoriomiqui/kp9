"""Conversión entre un `Request` y los campos de texto del editor integrado."""

from __future__ import annotations

import json
from typing import Any, cast

from kp9.model import Body, BodyType, HttpMethod, Request

_OBJECT_BODIES = ("form-urlencoded", "multipart")


class FormError(Exception):
    """Un campo del formulario no se puede convertir."""


def pairs_to_text(pairs: dict[str, str]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in pairs.items())


def text_to_pairs(text: str, field: str) -> dict[str, str]:
    """Una línea `nombre: valor` por entrada. Ignora líneas vacías y las que empiezan con #."""
    out: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            raise FormError(f"{field}, línea {number}: falta ':' (formato nombre: valor)")
        if not key.strip():
            raise FormError(f"{field}, línea {number}: falta el nombre")
        out[key.strip()] = value.strip()
    return out


def body_to_text(body: Body) -> str:
    if body.content is None or body.type == "none":
        return ""
    if body.type == "text":
        return str(body.content)
    return json.dumps(body.content, indent=2, ensure_ascii=False)


def text_to_body(body_type: str, text: str) -> Body:
    kind = cast(BodyType, body_type)
    if kind == "none":
        return Body()
    if kind == "text":
        return Body(type="text", content=text)
    if not text.strip():
        return Body(type=kind, content=None)
    try:
        content: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FormError(f"body, línea {exc.lineno}, columna {exc.colno}: {exc.msg}") from exc
    if kind in _OBJECT_BODIES and not isinstance(content, dict):
        raise FormError(f'body: en {kind} debe ser un objeto JSON {{"campo": "valor"}}')
    return Body(type=kind, content=content)


def build_request(
    original: Request,
    *,
    method: str,
    url: str,
    params_text: str,
    headers_text: str,
    body_type: str,
    body_text: str,
) -> Request:
    """Request editado; conserva nombre, descripción y auth del original."""
    return original.model_copy(
        update={
            "method": cast(HttpMethod, method),
            "url": url.strip(),
            "params": text_to_pairs(params_text, "params"),
            "headers": text_to_pairs(headers_text, "headers"),
            "body": text_to_body(body_type, body_text),
        }
    )
