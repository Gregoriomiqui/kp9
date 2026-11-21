import stat

import pytest

from kp9.model import Environment
from kp9.secrets import SecretsError, env_values, load_secrets, save_secrets, sensitive_values

ENV = Environment.model_validate(
    {
        "name": "qa",
        "variables": {
            "a": "1",
            "t": {"secret": True},
            "c": "$ENV:CID",
            "m": "$ENV:MISSING",
            "s2": {"secret": True},
        },
    }
)


def test_load_secrets_missing_file_returns_empty(tmp_path):
    assert load_secrets(tmp_path) == {}


def test_env_values_resolves_plain_secret_and_env():
    values = env_values(ENV, {"qa": {"t": "tok"}}, {"CID": "cid-1"})
    assert values == {"a": "1", "t": "tok", "c": "cid-1"}


def test_env_values_without_env_is_empty():
    assert env_values(None, {}, {}) == {}


def test_sensitive_values_only_secrets_and_env_refs():
    assert sorted(sensitive_values(ENV, {"qa": {"t": "tok"}}, {"CID": "cid-1"})) == ["cid-1", "tok"]


def test_save_secrets_roundtrip_and_permissions(tmp_path):
    save_secrets(tmp_path, {"qa": {"t": "x"}})
    assert load_secrets(tmp_path) == {"qa": {"t": "x"}}
    mode = stat.S_IMODE((tmp_path / ".kp9" / "secrets.json").stat().st_mode)
    assert mode == 0o600


def test_invalid_secrets_file_raises_with_location(tmp_path):
    (tmp_path / ".kp9").mkdir()
    (tmp_path / ".kp9" / "secrets.json").write_text("{")
    with pytest.raises(SecretsError, match=r"secrets\.json:1:2"):
        load_secrets(tmp_path)
