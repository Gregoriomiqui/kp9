"""Ejecución HTTP con httpx y representación de la respuesta."""

from __future__ import annotations

import json
import re
import shlex
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

from kp9.model import Body
from kp9.resolve import ResolvedRequest

FailureKind = Literal["timeout", "network", "tls", "body"]
_CHARSET = re.compile(r"charset=([\w.:-]+)", re.IGNORECASE)
_TEXT_TYPES = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded")
_BINARY_TYPES = (
    "image/",
    "audio/",
    "video/",
    "font/",
    "octet-stream",
    "pdf",
    "zip",
    "gzip",
    "protobuf",
)


class RequestFailed(Exception):
    def __init__(self, kind: FailureKind, message: str) -> None:
        super().__init__(message)
        self.kind: FailureKind = kind


@dataclass(frozen=True)
class Response:
    status: int
    reason: str
    headers: list[tuple[str, str]]
    body: bytes
    elapsed_ms: float
    encoding: str | None = None

    @property
    def size(self) -> int:
        return len(self.body)

    def header(self, name: str) -> str | None:
        lname = name.lower()
        return next((v for k, v in self.headers if k.lower() == lname), None)

    @property
    def content_type(self) -> str:
        return (self.header("content-type") or "").lower()

    @property
    def is_json(self) -> bool:
        return "json" in self.content_type

    @property
    def is_binary(self) -> bool:
        ctype = self.content_type
        if any(marker in ctype for marker in _TEXT_TYPES):
            return False
        if any(marker in ctype for marker in _BINARY_TYPES):
            return True
        return b"\x00" in self.body[:1024] or not self.decodes_cleanly()

    def _encoding(self) -> str:
        match = _CHARSET.search(self.content_type)
        return self.encoding or (match.group(1) if match else None) or "utf-8"

    def decodes_cleanly(self) -> bool:
        """True si el body es texto válido en su charset declarado (o UTF-8)."""
        try:
            self.body.decode(self._encoding())
        except (LookupError, UnicodeDecodeError):
            return False
        return True

    def text(self) -> str:
        try:
            return self.body.decode(self._encoding(), errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def pretty(self) -> str:
        if self.is_binary:
            return f"‹contenido binario, {self.size} bytes›"
        text = self.text()
        try:
            return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except ValueError:
            return text


def full_url(req: ResolvedRequest) -> str:
    if not req.params:
        return req.url
    separator = "&" if "?" in req.url else "?"
    return f"{req.url}{separator}{urlencode(req.params)}"


def _mapping(body: Body) -> Mapping[str, Any]:
    if body.content is None:
        return {}
    if not isinstance(body.content, dict):
        raise RequestFailed("body", f"el body {body.type} debe ser un objeto JSON")
    return body.content


def _multipart(body: Body) -> list[tuple[str, tuple[str | None, bytes | str]]]:
    files: list[tuple[str, tuple[str | None, bytes | str]]] = []
    for key, value in _mapping(body).items():
        text = str(value)
        if text.startswith("@"):
            path = Path(text[1:]).expanduser()
            try:
                files.append((key, (path.name, path.read_bytes())))
            except OSError as exc:
                raise RequestFailed("body", f"no se pudo leer {path}: {exc.strerror}") from exc
        else:
            files.append((key, (None, text)))
    return files


def _body_kwargs(body: Body) -> dict[str, Any]:
    if body.type == "json":
        return {"json": body.content}
    if body.type == "text":
        return {"content": ("" if body.content is None else str(body.content)).encode("utf-8")}
    if body.type == "form-urlencoded":
        return {"data": {k: str(v) for k, v in _mapping(body).items()}}
    if body.type == "multipart":
        return {"files": _multipart(body)}
    return {}


def _is_tls(exc: Exception) -> bool:
    cause = exc.__cause__ or exc.__context__
    message = str(exc).lower()
    return isinstance(cause, ssl.SSLError) or "ssl" in message or "certificate" in message


async def send(req: ResolvedRequest, client: httpx.AsyncClient, timeout: float) -> Response:
    kwargs = _body_kwargs(req.body)
    try:
        request = client.build_request(
            req.method,
            req.url,
            params=req.params or None,
            headers=[(k.encode("ascii"), v.encode("utf-8")) for k, v in req.headers.items()],
            timeout=timeout,
            **kwargs,
        )
    except httpx.InvalidURL as exc:
        raise RequestFailed("network", str(exc) or type(exc).__name__) from exc
    except (UnicodeEncodeError, ValueError, TypeError) as exc:
        raise RequestFailed("body", f"request inválido: {exc}") from exc
    try:
        started = time.perf_counter()
        raw = await client.send(request)
        elapsed = (time.perf_counter() - started) * 1000
    except httpx.TimeoutException as exc:
        raise RequestFailed("timeout", f"timeout tras {timeout:g} s") from exc
    except httpx.ConnectError as exc:
        kind: FailureKind = "tls" if _is_tls(exc) else "network"
        raise RequestFailed(kind, str(exc) or type(exc).__name__) from exc
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise RequestFailed("network", str(exc) or type(exc).__name__) from exc
    return Response(
        status=raw.status_code,
        reason=raw.reason_phrase,
        headers=list(raw.headers.multi_items()),
        body=raw.content,
        elapsed_ms=elapsed,
    )


def to_curl(req: ResolvedRequest) -> str:
    parts = ["curl", "-X", req.method, shlex.quote(full_url(req))]
    headers = dict(req.headers)
    if req.body.type == "json" and not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = "application/json"
    for key, value in headers.items():
        parts += ["-H", shlex.quote(f"{key}: {value}")]
    content = req.body.content
    if req.body.type == "json":
        parts += ["--data-raw", shlex.quote(json.dumps(content, ensure_ascii=False))]
    elif req.body.type == "text":
        parts += ["--data-raw", shlex.quote("" if content is None else str(content))]
    elif req.body.type == "form-urlencoded":
        for key, value in (content or {}).items():
            parts += ["--data-urlencode", shlex.quote(f"{key}={value}")]
    elif req.body.type == "multipart":
        for key, value in (content or {}).items():
            parts += ["-F", shlex.quote(f"{key}={value}")]
    return " ".join(parts)
