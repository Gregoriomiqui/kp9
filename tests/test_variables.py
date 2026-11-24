from kp9.model import CollectionMeta, Environment, FolderMeta, GroupMeta, SecretRef
from kp9.redact import MASK
from kp9.variables import VariableInfo, available_variables, completion_prefix, filter_variables

CHAIN = [
    GroupMeta(name="Pagos", variables={"g": "G", "shared": "group"}),
    CollectionMeta(name="Checkout API", baseUrl="https://col", variables={"apiVersion": "v1"}),
    FolderMeta(name="carrito", variables={"shared": "folder"}),
]
ENV = Environment(
    name="qa",
    variables={
        "baseUrl": "https://qa",
        "token": SecretRef(secret=True),
        "missing": SecretRef(secret=True),
        "cid": "$ENV:CID",
    },
)


def test_available_variables_follow_precedence_and_sources():
    infos = available_variables(CHAIN, ENV, {"qa": {"token": "t0k"}}, {"CID": "abc"})
    by_name = {i.name: i for i in infos}
    assert by_name["baseUrl"] == VariableInfo("baseUrl", "https://qa", "env qa")
    assert by_name["shared"] == VariableInfo("shared", "folder", "carpeta carrito")
    assert by_name["g"].source == "grupo Pagos"
    assert by_name["apiVersion"].source == "colección Checkout API"
    assert by_name["token"].display == MASK
    assert by_name["cid"].display == MASK
    assert by_name["missing"].display == "(sin valor)"
    assert [i.name for i in infos] == sorted(by_name, key=str.lower)


def test_available_variables_without_env():
    infos = available_variables(CHAIN, None, {}, {})
    assert {i.name for i in infos} == {"g", "shared", "baseUrl", "apiVersion"}
    assert next(i for i in infos if i.name == "baseUrl").source == "colección Checkout API"


def test_completion_prefix():
    assert completion_prefix("{{") == ""
    assert completion_prefix("{{base") == "base"
    assert completion_prefix("x/{{baseUrl}}/{{sk") == "sk"
    assert completion_prefix("{{baseUrl}}") is None
    assert completion_prefix("{{a b") is None
    assert completion_prefix("{") is None
    assert completion_prefix("") is None


def test_filter_variables_prefix_first_then_contains():
    infos = [
        VariableInfo(n, "v", "env") for n in ("apiVersion", "baseUrl", "sku", "skuPromo", "token")
    ]
    assert [i.name for i in filter_variables(infos, "")] == [i.name for i in infos]
    assert [i.name for i in filter_variables(infos, "sk")] == ["sku", "skuPromo"]
    assert [i.name for i in filter_variables(infos, "ver")] == ["apiVersion"]
    assert [i.name for i in filter_variables(infos, "URL")] == ["baseUrl"]
    assert filter_variables(infos, "zzz") == []


async def test_runner_variables_for_request(sample_ws):
    import httpx

    from kp9.history import History
    from kp9.runner import Runner
    from kp9.store import load_workspace

    ws = load_workspace(sample_ws)
    node = ws.node_at(sample_ws / "groups/pagos/checkout-api/carrito/ver-carrito.json")
    async with httpx.AsyncClient() as client:
        runner = Runner(ws, History(sample_ws / ".kp9" / "h.db"), client, environ={})
        by_name = {i.name: i for i in runner.variables_for(node, "qa")}
        assert by_name["sku"].value == "SKU-1"
        assert by_name["token"].display == MASK and by_name["token"].value == "qa-secret-token"
        assert by_name["apiVersion"].source == "colección Checkout API"
        (sample_ws / ".kp9" / "secrets.json").write_text("{roto")
        assert by_name.keys() == {i.name for i in runner.variables_for(node, "qa")}
