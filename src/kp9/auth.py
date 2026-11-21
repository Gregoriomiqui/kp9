"""Aplicación de credenciales a un request resuelto."""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

import httpx

from kp9.model import AuthApiKey, AuthBasic, AuthBearer, AuthOAuth2CC
from kp9.resolve import ResolvedRequest

DEFAULT_TOKEN_TTL = 3600.0
REFRESH_MARGIN = 30.0
TokenKey = tuple[str, str, str]


class AuthError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class _CachedToken:
    value: str
    expires_at: float


class TokenCache:
    """Cache en memoria de tokens OAuth2; expira REFRESH_MARGIN s antes."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._tokens: dict[TokenKey, _CachedToken] = {}

    def get(self, key: TokenKey) -> str | None:
        token = self._tokens.get(key)
        if token is not None and token.expires_at > self._clock():
            return token.value
        return None

    def put(self, key: TokenKey, value: str, ttl: float) -> None:
        self._tokens[key] = _CachedToken(value, self._clock() + max(ttl - REFRESH_MARGIN, 0.0))

    def clear(self) -> None:
        self._tokens.clear()


def _set_header(headers: dict[str, str], name: str, value: str) -> None:
    for existing in [k for k in headers if k.lower() == name.lower()]:
        del headers[existing]
    headers[name] = value


async def fetch_token(auth: AuthOAuth2CC, client: httpx.AsyncClient, cache: TokenCache) -> str:
    key: TokenKey = (auth.tokenUrl, auth.clientId, " ".join(auth.scopes))
    cached = cache.get(key)
    if cached is not None:
        return cached
    form = {
        "grant_type": "client_credentials",
        "client_id": auth.clientId,
        "client_secret": auth.clientSecret,
    }
    if auth.scopes:
        form["scope"] = " ".join(auth.scopes)
    try:
        response = await client.post(
            auth.tokenUrl, data=form, headers={"Accept": "application/json"}
        )
    except httpx.HTTPError as exc:
        raise AuthError(f"no se pudo contactar el token endpoint: {exc}") from exc
    if response.status_code >= 400:
        raise AuthError(
            f"token endpoint respondió {response.status_code}", response.status_code, response.text
        )
    try:
        payload = response.json()
        token = str(payload["access_token"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AuthError(
            "respuesta del token endpoint sin access_token", response.status_code, response.text
        ) from exc
    try:
        ttl = float(payload.get("expires_in", DEFAULT_TOKEN_TTL))
    except (TypeError, ValueError):
        ttl = DEFAULT_TOKEN_TTL
    cache.put(key, token, ttl)
    return token


async def apply_auth(
    req: ResolvedRequest, client: httpx.AsyncClient, cache: TokenCache
) -> ResolvedRequest:
    auth = req.auth
    headers = dict(req.headers)
    params = dict(req.params)
    if isinstance(auth, AuthBearer):
        _set_header(headers, "Authorization", f"Bearer {auth.token}")
    elif isinstance(auth, AuthBasic):
        raw = f"{auth.username}:{auth.password}".encode()
        _set_header(headers, "Authorization", "Basic " + base64.b64encode(raw).decode("ascii"))
    elif isinstance(auth, AuthApiKey):
        if auth.in_ == "query":
            params[auth.key] = auth.value
        else:
            _set_header(headers, auth.key, auth.value)
    elif isinstance(auth, AuthOAuth2CC):
        _set_header(headers, "Authorization", f"Bearer {await fetch_token(auth, client, cache)}")
    else:
        return req
    return replace(req, headers=headers, params=params)
