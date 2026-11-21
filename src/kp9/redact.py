"""Redacción de datos sensibles antes de persistir."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import quote, quote_plus

MASK = "••••"
DEFAULT_SENSITIVE_HEADERS = ("authorization", "cookie", "set-cookie", "x-api-key")

HeadersLike = Mapping[str, str] | Iterable[tuple[str, str]]


class Redactor:
    def __init__(self, secrets: Iterable[str] = (), extra_headers: Iterable[str] = ()) -> None:
        self._raw = [s for s in secrets if s]
        self._extra_headers = tuple(extra_headers)
        variants: set[str] = set()
        for secret in self._raw:
            variants.update(_variants(secret))
        self._secrets = sorted(variants, key=len, reverse=True)
        self._secret_bytes = sorted({v.encode("utf-8") for v in variants}, key=len, reverse=True)
        self._headers = {h.lower() for h in (*DEFAULT_SENSITIVE_HEADERS, *self._extra_headers)}

    def with_secrets(self, extra: Iterable[str]) -> Redactor:
        """Copia que además oculta `extra` (p. ej. credenciales que agrega la auth)."""
        return Redactor([*self._raw, *extra], self._extra_headers)

    def is_sensitive_header(self, name: str) -> bool:
        return name.lower() in self._headers

    def bytes(self, value: bytes) -> bytes:
        for secret in self._secret_bytes:
            value = value.replace(secret, MASK.encode("utf-8"))
        return value

    def text(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, MASK)
        return value

    def headers(self, headers: HeadersLike) -> list[tuple[str, str]]:
        items = headers.items() if isinstance(headers, Mapping) else headers
        return [(k, MASK if k.lower() in self._headers else self.text(v)) for k, v in items]

    def value(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            return {self.text(str(k)): self.value(v) for k, v in obj.items()}
        if isinstance(obj, list | tuple):
            return [self.value(v) for v in obj]
        return obj


def _variants(secret: str) -> set[str]:
    """Formas en que un secreto suele reaparecer: URL-encoded y escapado en JSON."""
    out = {secret, quote(secret, safe=""), quote_plus(secret, safe=""), quote(secret)}
    for ascii_only in (True, False):
        escaped = json.dumps(secret, ensure_ascii=ascii_only)[1:-1]
        out.update({escaped, escaped.replace("/", "\\/")})
    return {v for v in out if v}
