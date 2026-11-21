import asyncio

import httpx
import pytest

from kp9.auth import TokenCache
from kp9.history import History
from kp9.model import AuthBearer, AuthNone, AuthOAuth2CC, Body
from kp9.resolve import ResolvedRequest, ResolveError
from kp9.runner import NotSendable, Runner
from kp9.store import RequestNode, load_workspace

CARRITO = "groups/pagos/checkout-api/carrito"
VER = f"{CARRITO}/ver-carrito.json"
AGREGAR = f"{CARRITO}/agregar-al-carrito.json"
BUSCAR = "groups/pagos/checkout-api/buscar.json"


@pytest.fixture
def ws(sample_ws):
    return load_workspace(sample_ws)


@pytest.fixture
def history(tmp_path):
    h = History(tmp_path / "h.db")
    yield h
    h.close()


@pytest.fixture
async def client(recorder):
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as c:
        yield c


def node(ws, rel):
    n = ws.node_at(ws.root / rel)
    assert isinstance(n, RequestNode)
    return n


def runner_for(ws, history, client):
    return Runner(ws, history, client, TokenCache(), environ={})


def test_prepare_resolves_with_active_env(ws, history, client):
    r = runner_for(ws, history, client).prepare(node(ws, AGREGAR), "qa")
    assert r.url == "https://qa.example.com/v1/cart/items"
    assert r.body.content == {"sku": "SKU-1", "qty": 1}
    assert r.auth == AuthBearer(token="qa-secret-token")


def test_prepare_missing_variable(ws, history, client):
    with pytest.raises(ResolveError, match=r"^\{\{query\}\} no definida en qa$"):
        runner_for(ws, history, client).prepare(node(ws, BUSCAR), "qa")


def test_prepare_unknown_env_means_no_env(ws, history, client):
    with pytest.raises(ResolveError, match="sin entorno activo"):
        runner_for(ws, history, client).prepare(node(ws, VER), None)


def test_prepare_invalid_node_raises_not_sendable(ws, history, client):
    bad = RequestNode(path=ws.root / "x.json", request=None, error="x.json:1:1: roto", chain=[])
    with pytest.raises(NotSendable, match="roto"):
        runner_for(ws, history, client).prepare(bad, "qa")


def test_invalid_secrets_file_raises_not_sendable(ws, history, client):
    (ws.root / ".kp9" / "secrets.json").write_text("{")
    with pytest.raises(NotSendable, match="secrets.json:1:2"):
        runner_for(ws, history, client).prepare(node(ws, VER), "qa")


def test_needs_confirmation(ws, history, client):
    r = runner_for(ws, history, client)
    post = r.prepare(node(ws, AGREGAR), "prod")
    get = r.prepare(node(ws, VER), "prod")
    assert r.needs_confirmation(post, "prod") is True
    assert r.needs_confirmation(get, "prod") is False
    assert r.needs_confirmation(post, "qa") is False
    assert r.needs_confirmation(post, None) is False


async def test_execute_records_redacted_history(ws, history, client, recorder):
    r = runner_for(ws, history, client)
    outcome = await r.execute(r.prepare(node(ws, VER), "qa"), "qa", ws.root / VER)
    assert outcome.response is not None and outcome.response.status == 200
    assert outcome.error is None
    [sent] = recorder.requests
    assert sent.headers["authorization"] == "Bearer qa-secret-token"
    entry = history.get(outcome.history_id)
    assert entry.request_path == VER
    assert entry.env == "qa"
    assert "qa-secret-token" not in entry.request_json


async def test_execute_redacts_secret_echoed_in_response(ws, history, client, recorder):
    recorder.responder = lambda req: httpx.Response(
        200, json={"echo": req.headers["authorization"]}
    )
    r = runner_for(ws, history, client)
    outcome = await r.execute(r.prepare(node(ws, VER), "qa"), "qa", ws.root / VER)
    assert "qa-secret-token" in outcome.response.text()
    assert "qa-secret-token" not in history.get(outcome.history_id).response().text()


async def test_execute_network_error(ws, history):
    def boom(request):
        raise httpx.ConnectError("sin red", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as c:
        r = runner_for(ws, history, c)
        outcome = await r.execute(r.prepare(node(ws, VER), "qa"), "qa", ws.root / VER)
    assert outcome.response is None
    assert outcome.error == "network: sin red"
    assert history.get(outcome.history_id).status is None


async def test_execute_cancel_records_cancelled(ws, history):
    async def slow(request):
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as c:
        r = runner_for(ws, history, c)
        task = asyncio.create_task(r.execute(r.prepare(node(ws, VER), "qa"), "qa", ws.root / VER))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert history.list()[0].error == "cancelado"


async def test_execute_auth_error_is_redacted(ws, history):
    def token_endpoint(request):
        return httpx.Response(401, text="bad client qa-secret-token")

    async with httpx.AsyncClient(transport=httpx.MockTransport(token_endpoint)) as c:
        r = runner_for(ws, history, c)
        resolved = ResolvedRequest(
            method="GET",
            url="https://api.test/me",
            params={},
            headers={},
            body=Body(),
            auth=AuthOAuth2CC(
                tokenUrl="https://auth.test/token",
                clientId="cid",
                clientSecret="qa-secret-token",
            ),
        )
        outcome = await r.execute(resolved, "qa", None)
    assert outcome.error.startswith("token endpoint respondió 401")
    assert "qa-secret-token" not in outcome.error
    assert "qa-secret-token" not in history.get(outcome.history_id).error


async def test_execute_without_auth(ws, history, client, recorder):
    r = runner_for(ws, history, client)
    resolved = ResolvedRequest("GET", "https://api.test/x", {}, {}, Body(), AuthNone())
    outcome = await r.execute(resolved, None, None)
    assert outcome.response.status == 200
    assert "authorization" not in recorder.requests[0].headers
