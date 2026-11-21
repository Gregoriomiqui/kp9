from urllib.parse import parse_qsl

import httpx
import pytest
import respx

from kp9.auth import AuthError, TokenCache, apply_auth
from kp9.model import AuthApiKey, AuthBasic, AuthBearer, AuthNone, AuthOAuth2CC, Body
from kp9.resolve import ResolvedRequest

TOKEN_URL = "https://auth.test/token"


def rr(auth, headers=None, params=None):
    return ResolvedRequest(
        method="GET",
        url="https://api.test/x",
        params=params or {},
        headers=headers or {},
        body=Body(),
        auth=auth,
    )


def oauth(scopes=("read", "write")):
    return AuthOAuth2CC(tokenUrl=TOKEN_URL, clientId="cid", clientSecret="cs", scopes=list(scopes))


async def test_none_returns_same_request():
    async with httpx.AsyncClient() as c:
        assert await apply_auth(rr(AuthNone()), c, TokenCache()) == rr(AuthNone())


async def test_bearer_replaces_existing_header_case_insensitive():
    async with httpx.AsyncClient() as c:
        out = await apply_auth(
            rr(AuthBearer(token="T"), headers={"authorization": "old"}), c, TokenCache()
        )
    assert out.headers == {"Authorization": "Bearer T"}


async def test_basic():
    async with httpx.AsyncClient() as c:
        out = await apply_auth(rr(AuthBasic(username="u", password="p")), c, TokenCache())
    assert out.headers["Authorization"] == "Basic dTpw"


async def test_apikey_header_and_query():
    header = AuthApiKey.model_validate({"type": "apikey", "key": "X-Api-Key", "value": "v"})
    query = AuthApiKey.model_validate({"type": "apikey", "key": "k", "value": "v", "in": "query"})
    async with httpx.AsyncClient() as c:
        assert (await apply_auth(rr(header), c, TokenCache())).headers == {"X-Api-Key": "v"}
        out = await apply_auth(rr(query), c, TokenCache())
    assert out.params == {"k": "v"}
    assert out.headers == {}


@respx.mock
async def test_oauth2_fetches_and_caches():
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "AT", "expires_in": 3600})
    )
    cache = TokenCache()
    async with httpx.AsyncClient() as c:
        first = await apply_auth(rr(oauth()), c, cache)
        second = await apply_auth(rr(oauth()), c, cache)
    assert first.headers["Authorization"] == "Bearer AT"
    assert second.headers["Authorization"] == "Bearer AT"
    assert route.call_count == 1
    form = dict(parse_qsl(route.calls.last.request.content.decode()))
    assert form == {
        "grant_type": "client_credentials",
        "client_id": "cid",
        "client_secret": "cs",
        "scope": "read write",
    }


@respx.mock
async def test_oauth2_refetches_after_expiry():
    now = [1000.0]
    cache = TokenCache(clock=lambda: now[0])
    respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "A1", "expires_in": 60}),
            httpx.Response(200, json={"access_token": "A2", "expires_in": 60}),
        ]
    )
    async with httpx.AsyncClient() as c:
        assert (await apply_auth(rr(oauth()), c, cache)).headers["Authorization"] == "Bearer A1"
        now[0] += 31
        assert (await apply_auth(rr(oauth()), c, cache)).headers["Authorization"] == "Bearer A2"


@respx.mock
async def test_oauth2_without_expires_in_uses_default_ttl():
    now = [0.0]
    cache = TokenCache(clock=lambda: now[0])
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "A"}))
    async with httpx.AsyncClient() as c:
        await apply_auth(rr(oauth()), c, cache)
        now[0] += 3000
        await apply_auth(rr(oauth()), c, cache)
    assert route.call_count == 1


@respx.mock
async def test_oauth2_error_status():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401, text="invalid_client"))
    async with httpx.AsyncClient() as c:
        with pytest.raises(AuthError) as exc:
            await apply_auth(rr(oauth()), c, TokenCache())
    assert str(exc.value) == "token endpoint respondió 401"
    assert exc.value.status == 401
    assert exc.value.body == "invalid_client"


@respx.mock
async def test_oauth2_without_access_token():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"token": "x"}))
    async with httpx.AsyncClient() as c:
        with pytest.raises(AuthError, match="sin access_token"):
            await apply_auth(rr(oauth()), c, TokenCache())


@respx.mock
async def test_oauth2_network_error():
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("caído"))
    async with httpx.AsyncClient() as c:
        with pytest.raises(AuthError, match="^no se pudo contactar el token endpoint"):
            await apply_auth(rr(oauth()), c, TokenCache())
