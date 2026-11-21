"""Fusión de capas y sustitución de {{variables}}. Puro: sin IO."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kp9.model import Auth, AuthInherit, AuthNone, Body, CollectionMeta, NodeMeta, Request

_VAR = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")


class ResolveError(Exception):
    def __init__(
        self, missing: list[str], env_name: str | None, cycle: list[str] | None = None
    ) -> None:
        self.missing = missing
        self.env_name = env_name
        self.cycle = cycle
        super().__init__(self._message())

    def _message(self) -> str:
        if self.cycle:
            return "referencia circular: " + " → ".join(self.cycle)
        names = ", ".join("{{" + name + "}}" for name in self.missing)
        verb = "no definida" if len(self.missing) == 1 else "no definidas"
        where = f"en {self.env_name}" if self.env_name else "(sin entorno activo)"
        return f"{names} {verb} {where}"


class _Cycle(Exception):
    def __init__(self, path: list[str]) -> None:
        super().__init__(" → ".join(path))
        self.path = path


@dataclass(frozen=True)
class ResolvedRequest:
    method: str
    url: str
    params: dict[str, str]
    headers: dict[str, str]
    body: Body
    auth: Auth


def merge_variables(chain: list[NodeMeta], env_vars: Mapping[str, str]) -> dict[str, str]:
    """Grupo < colección < carpetas (externa→interna) < entorno activo, como en Postman."""
    merged: dict[str, str] = {}
    for meta in chain:
        if isinstance(meta, CollectionMeta) and meta.baseUrl is not None:
            merged["baseUrl"] = meta.baseUrl
        merged.update(meta.variables)
    merged.update(env_vars)
    return merged


def effective_auth(request: Request, chain: list[NodeMeta]) -> Auth:
    if not isinstance(request.auth, AuthInherit):
        return request.auth
    for meta in reversed(chain):
        if meta.auth is not None and not isinstance(meta.auth, AuthInherit):
            return meta.auth
    return AuthNone()


class _Substitution:
    def __init__(self, variables: Mapping[str, str]) -> None:
        self.variables = variables
        self.missing: list[str] = []

    def text(self, value: str, stack: tuple[str, ...] = ()) -> str:
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name in stack:
                raise _Cycle([*stack, name])
            if name not in self.variables:
                if name not in self.missing:
                    self.missing.append(name)
                return match.group(0)
            return self.text(self.variables[name], (*stack, name))

        return _VAR.sub(replace, value)

    def value(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            return {self.text(str(k)): self.value(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.value(v) for v in obj]
        return obj


def _substitute_auth(auth: Auth, sub: _Substitution) -> Auth:
    data = auth.model_dump(by_alias=True)
    resolved = {k: (v if k == "type" else sub.value(v)) for k, v in data.items()}
    return type(auth).model_validate(resolved)


def resolve(
    request: Request,
    chain: list[NodeMeta],
    env_vars: Mapping[str, str],
    env_name: str | None,
) -> ResolvedRequest:
    sub = _Substitution(merge_variables(chain, env_vars))
    try:
        url = sub.text(request.url)
        params = {sub.text(k): sub.text(v) for k, v in request.params.items()}
        headers = {sub.text(k): sub.text(v) for k, v in request.headers.items()}
        body = Body(type=request.body.type, content=sub.value(request.body.content))
        auth = _substitute_auth(effective_auth(request, chain), sub)
    except _Cycle as cycle:
        raise ResolveError([], env_name, cycle=cycle.path) from None
    if sub.missing:
        raise ResolveError(sub.missing, env_name)
    return ResolvedRequest(request.method, url, params, headers, body, auth)
