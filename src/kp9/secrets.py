"""Valores secretos locales (.kp9/secrets.json) y referencias $ENV:."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from kp9.model import Environment, SecretRef
from kp9.store import LOCAL_DIR

ENV_PREFIX = "$ENV:"
Secrets = dict[str, dict[str, str]]


class SecretsError(Exception):
    """secrets.json no se puede leer."""


def secrets_path(root: Path) -> Path:
    return root / LOCAL_DIR / "secrets.json"


def load_secrets(root: Path) -> Secrets:
    path = secrets_path(root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SecretsError(f"{path}:{exc.lineno}:{exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise SecretsError(f"{path}: se esperaba un objeto JSON")
    return {
        str(env): {str(k): str(v) for k, v in values.items() if v is not None}
        for env, values in data.items()
        if isinstance(values, dict)
    }


def save_secrets(root: Path, data: Secrets) -> None:
    path = secrets_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _lookup(
    env: Environment,
    name: str,
    value: str | SecretRef,
    secrets: Secrets,
    environ: Mapping[str, str],
) -> tuple[str | None, bool]:
    """Devuelve (valor, es_sensible)."""
    if isinstance(value, SecretRef):
        # un secreto vacío cuenta como no definido (spec §3.5)
        return secrets.get(env.name, {}).get(name) or None, True
    if value.startswith(ENV_PREFIX):
        return environ.get(value[len(ENV_PREFIX) :]) or None, True
    return value, False


def env_values(
    env: Environment | None, secrets: Secrets, environ: Mapping[str, str]
) -> dict[str, str]:
    if env is None:
        return {}
    out: dict[str, str] = {}
    for name, raw in env.variables.items():
        value, _ = _lookup(env, name, raw, secrets, environ)
        if value is not None:
            out[name] = value
    return out


def sensitive_values(
    env: Environment | None, secrets: Secrets, environ: Mapping[str, str]
) -> list[str]:
    if env is None:
        return []
    out: list[str] = []
    for name, raw in env.variables.items():
        value, sensitive = _lookup(env, name, raw, secrets, environ)
        if sensitive and value:
            out.append(value)
    return out
