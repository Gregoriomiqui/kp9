"""Variables disponibles para un request (para autocompletar `{{...}}`)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from kp9.model import CollectionMeta, Environment, FolderMeta, GroupMeta, NodeMeta, SecretRef
from kp9.redact import MASK
from kp9.secrets import ENV_PREFIX, Secrets

NO_VALUE = "(sin valor)"
_OPEN = re.compile(r"\{\{([^{}\s]*)$")


@dataclass(frozen=True)
class VariableInfo:
    name: str
    value: str | None
    source: str
    sensitive: bool = False

    @property
    def display(self) -> str:
        """Valor para mostrar: secretos ocultos y `(sin valor)` si no se resuelve."""
        if self.value is None:
            return NO_VALUE
        return MASK if self.sensitive else self.value


def _layer_label(meta: NodeMeta) -> str:
    if isinstance(meta, GroupMeta):
        return f"grupo {meta.name}"
    if isinstance(meta, CollectionMeta):
        return f"colección {meta.name}"
    if isinstance(meta, FolderMeta):
        return f"carpeta {meta.name}"
    return meta.name


def available_variables(
    chain: list[NodeMeta],
    env: Environment | None,
    secrets: Secrets,
    environ: Mapping[str, str],
) -> list[VariableInfo]:
    """Una entrada por nombre, con la capa que gana (misma precedencia que `resolve`)."""
    found: dict[str, VariableInfo] = {}
    for meta in chain:
        label = _layer_label(meta)
        if isinstance(meta, CollectionMeta) and meta.baseUrl is not None:
            found["baseUrl"] = VariableInfo("baseUrl", meta.baseUrl, label)
        for name, value in meta.variables.items():
            found[name] = VariableInfo(name, value, label)
    if env is not None:
        label = f"env {env.name}"
        for name, raw in env.variables.items():
            if isinstance(raw, SecretRef):
                secret = secrets.get(env.name, {}).get(name) or None
                found[name] = VariableInfo(name, secret, label, sensitive=True)
            elif raw.startswith(ENV_PREFIX):
                from_env = environ.get(raw[len(ENV_PREFIX) :]) or None
                found[name] = VariableInfo(name, from_env, label, sensitive=True)
            else:
                found[name] = VariableInfo(name, raw, label)
    return sorted(found.values(), key=lambda info: info.name.lower())


def completion_prefix(before_cursor: str) -> str | None:
    """Si el cursor está dentro de un `{{` sin cerrar, devuelve lo escrito tras él."""
    match = _OPEN.search(before_cursor)
    return match.group(1) if match else None


def filter_variables(infos: Iterable[VariableInfo], prefix: str) -> list[VariableInfo]:
    """Primero las que empiezan con `prefix`, después las que lo contienen (sin mayúsculas)."""
    needle = prefix.lower()
    items = list(infos)
    starts = [i for i in items if i.name.lower().startswith(needle)]
    contains = [i for i in items if needle in i.name.lower() and i not in starts]
    return starts + contains
