import pytest

from kp9.model import (
    AuthBasic,
    AuthBearer,
    AuthNone,
    CollectionMeta,
    FolderMeta,
    GroupMeta,
    Request,
)
from kp9.resolve import ResolveError, effective_auth, merge_variables, resolve


def chain():
    return [
        GroupMeta(name="g", variables={"v": "group", "g": "G"}, auth=AuthBearer(token="{{token}}")),
        CollectionMeta(name="c", variables={"v": "collection"}),
        FolderMeta(name="outer", variables={"v": "outer"}),
        FolderMeta(name="inner", variables={"v": "inner"}),
    ]


def req(**kw):
    data = {"name": "r", "url": "https://x"}
    data.update(kw)
    return Request.model_validate(data)


def test_merge_most_specific_wins_without_env_value():
    variables = merge_variables(chain(), {"e": "E"})
    assert variables["v"] == "inner"
    assert variables["g"] == "G"
    assert variables["e"] == "E"


def test_env_overrides_hierarchy_like_postman():
    variables = merge_variables(chain(), {"v": "env"})
    assert variables["v"] == "env"
    assert variables["g"] == "G"


def test_collection_baseurl_becomes_variable():
    merged = merge_variables(
        [CollectionMeta(name="c", baseUrl="https://c")], {"baseUrl": "https://e"}
    )
    assert merged["baseUrl"] == "https://e"


def test_collection_baseurl_used_when_env_lacks_it():
    merged = merge_variables([CollectionMeta(name="c", baseUrl="https://c")], {})
    assert merged["baseUrl"] == "https://c"


def test_collection_variables_override_baseurl_field():
    meta = CollectionMeta(name="c", baseUrl="https://a", variables={"baseUrl": "https://b"})
    assert merge_variables([meta], {})["baseUrl"] == "https://b"


def test_resolve_substitutes_everywhere():
    r = resolve(
        req(
            method="POST",
            url="{{base}}/items/{{id}}",
            params={"q": "{{q}}"},
            headers={"X-Id": "{{id}}"},
            body={"type": "json", "content": {"id": "{{id}}", "qty": 1, "tags": ["{{q}}"]}},
        ),
        [],
        {"base": "https://x", "id": "42", "q": "hola"},
        "qa",
    )
    assert r.method == "POST"
    assert r.url == "https://x/items/42"
    assert r.params == {"q": "hola"}
    assert r.headers == {"X-Id": "42"}
    assert r.body.content == {"id": "42", "qty": 1, "tags": ["hola"]}


def test_whitespace_inside_braces():
    assert resolve(req(url="{{ base }}/x"), [], {"base": "https://h"}, "qa").url == "https://h/x"


def test_nested_variable_values():
    r = resolve(req(url="{{base}}/x"), [], {"base": "{{scheme}}://h", "scheme": "https"}, "qa")
    assert r.url == "https://h/x"


def test_cycle_raises_clear_error():
    with pytest.raises(ResolveError) as exc:
        resolve(req(url="{{a}}"), [], {"a": "{{b}}", "b": "{{a}}"}, "qa")
    assert str(exc.value) == "referencia circular: a → b → a"


def test_missing_variables_listed_once_each():
    with pytest.raises(ResolveError) as exc:
        resolve(req(url="{{a}}/{{b}}/{{a}}"), [], {}, "qa")
    assert exc.value.missing == ["a", "b"]
    assert str(exc.value) == "{{a}}, {{b}} no definidas en qa"


def test_missing_single_message_matches_spec():
    with pytest.raises(ResolveError, match=r"^\{\{sku\}\} no definida en qa$"):
        resolve(req(body={"type": "json", "content": {"sku": "{{sku}}"}}), [], {}, "qa")


def test_missing_without_env():
    with pytest.raises(ResolveError, match=r"\(sin entorno activo\)"):
        resolve(req(url="{{baseUrl}}/x"), [], {}, None)


def test_auth_inherit_walks_up():
    assert effective_auth(req(), chain()) == AuthBearer(token="{{token}}")


def test_auth_inner_folder_overrides():
    c = chain()
    c[-1] = FolderMeta(name="inner", auth=AuthBasic(username="u", password="p"))
    assert isinstance(effective_auth(req(), c), AuthBasic)


def test_auth_request_explicit_wins():
    assert isinstance(effective_auth(req(auth={"type": "none"}), chain()), AuthNone)


def test_auth_defaults_to_none():
    assert isinstance(effective_auth(req(), []), AuthNone)


def test_resolve_substitutes_auth_fields():
    assert resolve(req(), chain(), {"token": "T"}, "qa").auth == AuthBearer(token="T")


def test_missing_variable_inside_auth_reported():
    with pytest.raises(ResolveError) as exc:
        resolve(req(), chain(), {}, "qa")
    assert exc.value.missing == ["token"]
