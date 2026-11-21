import pytest
from pydantic import ValidationError

from kp9.model import (
    AuthApiKey,
    AuthBearer,
    AuthInherit,
    AuthOAuth2CC,
    CollectionMeta,
    Environment,
    Request,
    SecretRef,
    WorkspaceConfig,
    dump,
)


def test_request_example_from_spec_parses():
    req = Request.model_validate(
        {
            "name": "Agregar al carrito",
            "description": "Agrega un SKU al carrito activo",
            "method": "POST",
            "url": "{{baseUrl}}/v1/cart/items",
            "params": {"channel": "web"},
            "headers": {"Content-Type": "application/json"},
            "body": {"type": "json", "content": {"sku": "{{sku}}", "qty": 1}},
            "auth": {"type": "inherit"},
        }
    )
    assert req.method == "POST"
    assert req.body.content == {"sku": "{{sku}}", "qty": 1}
    assert isinstance(req.auth, AuthInherit)


def test_request_defaults():
    req = Request.model_validate({"name": "x", "url": "http://a"})
    assert req.method == "GET"
    assert req.body.type == "none"
    assert isinstance(req.auth, AuthInherit)
    assert req.params == {}
    assert req.headers == {}


def test_auth_discriminator_selects_type():
    req = Request.model_validate(
        {"name": "x", "url": "u", "auth": {"type": "bearer", "token": "{{token}}"}}
    )
    assert isinstance(req.auth, AuthBearer)
    assert req.auth.token == "{{token}}"


def test_apikey_in_alias_roundtrip():
    auth = AuthApiKey.model_validate(
        {"type": "apikey", "key": "X-Api-Key", "value": "v", "in": "query"}
    )
    assert auth.in_ == "query"
    assert dump(auth) == {"type": "apikey", "key": "X-Api-Key", "value": "v", "in": "query"}


def test_oauth2_scopes_default_empty():
    auth = AuthOAuth2CC.model_validate(
        {"type": "oauth2-cc", "tokenUrl": "t", "clientId": "c", "clientSecret": "s"}
    )
    assert auth.scopes == []


def test_invalid_method_reports_field():
    with pytest.raises(ValidationError) as exc:
        Request.model_validate({"name": "x", "url": "u", "method": "FETCH"})
    assert exc.value.errors()[0]["loc"] == ("method",)


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Request.model_validate({"name": "x", "url": "u", "metod": "GET"})


def test_environment_secret_ref_and_plain_values():
    env = Environment.model_validate(
        {
            "name": "prod",
            "protected": True,
            "variables": {
                "baseUrl": "https://api.example.com",
                "token": {"secret": True},
                "cid": "$ENV:KP9_PROD_CLIENT_ID",
            },
        }
    )
    assert env.protected is True
    assert isinstance(env.variables["token"], SecretRef)
    assert env.variables["cid"] == "$ENV:KP9_PROD_CLIENT_ID"


def test_environment_protected_is_opt_in():
    assert Environment.model_validate({"name": "prod"}).protected is False


def test_dump_omits_none_fields():
    assert dump(CollectionMeta(name="c")) == {"name": "c", "description": "", "variables": {}}


def test_workspace_config_defaults():
    cfg = WorkspaceConfig(name="w")
    assert cfg.timeout == 30.0
    assert cfg.redactHeaders == []
    assert cfg.defaultEnv is None
