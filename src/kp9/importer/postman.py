"""Importación de colecciones y entornos Postman v2.0/v2.1."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl

from kp9.model import (
    Auth,
    AuthApiKey,
    AuthBasic,
    AuthBearer,
    AuthInherit,
    AuthNone,
    AuthOAuth2CC,
    Body,
    CollectionMeta,
    Environment,
    FolderMeta,
    GroupMeta,
    HttpMethod,
    Request,
    SecretRef,
)
from kp9.secrets import SecretsError, load_secrets, save_secrets
from kp9.store import (
    COLLECTION_FILE,
    ENVIRONMENTS_DIR,
    FOLDER_FILE,
    GROUP_FILE,
    GROUPS_DIR,
    slugify,
    unique_path,
    write_json,
)

METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


class PostmanImportError(Exception):
    """El archivo no es importable."""


@dataclass
class ImportReport:
    target: Path | None = None
    requests: int = 0
    folders: int = 0
    environments: int = 0
    skipped: list[str] = field(default_factory=list)


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def is_environment(data: Any) -> bool:
    return isinstance(data, dict) and "values" in data and "item" not in data


def _description(raw: Any) -> str:
    if isinstance(raw, dict):
        return _s(raw.get("content"))
    return _s(raw)


def _pairs(raw: Any) -> dict[str, str]:
    return {
        str(e["key"]): _s(e.get("value"))
        for e in raw or []
        if isinstance(e, dict) and e.get("key") and not e.get("disabled")
    }


def _variables(raw: Any) -> dict[str, str]:
    return _pairs(raw)


def _note_events(obj: dict[str, Any], report: ImportReport, label: str) -> None:
    for event in obj.get("event") or []:
        if not isinstance(event, dict):
            continue
        script = (event.get("script") or {}).get("exec")
        code = "\n".join(script) if isinstance(script, list) else _s(script)
        if code.strip():
            report.skipped.append(f"{label}: script '{event.get('listen', '?')}' omitido")


def _auth_values(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): _s(v) for k, v in raw.items()}
    if isinstance(raw, list):
        return {
            str(e["key"]): _s(e.get("value")) for e in raw if isinstance(e, dict) and "key" in e
        }
    return {}


def _auth(raw: Any, report: ImportReport, label: str) -> Auth | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    values = _auth_values(raw.get(kind)) if isinstance(kind, str) else {}
    if kind == "noauth":
        return AuthNone()
    if kind == "bearer":
        return AuthBearer(token=values.get("token", ""))
    if kind == "basic":
        return AuthBasic(username=values.get("username", ""), password=values.get("password", ""))
    if kind == "apikey":
        return AuthApiKey.model_validate(
            {
                "type": "apikey",
                "key": values.get("key") or "X-Api-Key",
                "value": values.get("value", ""),
                "in": "query" if values.get("in") == "query" else "header",
            }
        )
    if kind == "oauth2":
        grant = values.get("grant_type", "?")
        if grant == "client_credentials":
            return AuthOAuth2CC(
                tokenUrl=values.get("accessTokenUrl", ""),
                clientId=values.get("clientId", ""),
                clientSecret=values.get("clientSecret", ""),
                scopes=values.get("scope", "").split(),
            )
        report.skipped.append(f"{label}: OAuth2 con grant '{grant}' no soportado")
        return None
    report.skipped.append(f"{label}: auth '{kind}' no soportada")
    return None


def _url(raw: Any) -> tuple[str, dict[str, str]]:
    if raw is None:
        return "", {}
    if isinstance(raw, str):
        text, query = raw, None
    else:
        text, query = _s(raw.get("raw")), raw.get("query")
    base, _, qs = text.partition("?")
    if query is not None:
        return base, _pairs(query)
    return base, dict(parse_qsl(qs, keep_blank_values=True))


def _body(raw: Any, report: ImportReport, label: str) -> tuple[Body, str | None]:
    """Devuelve (body, content-type a agregar si falta)."""
    if not isinstance(raw, dict) or raw.get("disabled"):
        return Body(), None
    mode = raw.get("mode")
    if mode == "raw":
        text = _s(raw.get("raw"))
        language = ((raw.get("options") or {}).get("raw") or {}).get("language")
        if language == "json":
            try:
                return Body(type="json", content=json.loads(text)), None
            except ValueError:
                report.skipped.append(
                    f"{label}: body JSON inválido (¿variables sin comillas?); importado como texto"
                )
                return Body(type="text", content=text), "application/json"
        return Body(type="text", content=text), None
    if mode == "urlencoded":
        return Body(type="form-urlencoded", content=_pairs(raw.get("urlencoded"))), None
    if mode == "formdata":
        fields: dict[str, str] = {}
        for entry in raw.get("formdata") or []:
            if not isinstance(entry, dict) or not entry.get("key") or entry.get("disabled"):
                continue
            key = str(entry["key"])
            if entry.get("type") == "file":
                src = entry.get("src")
                src = src[0] if isinstance(src, list) and src else src
                if not src:
                    report.skipped.append(f"{label}: campo de archivo '{key}' sin ruta")
                    continue
                fields[key] = f"@{src}"
            else:
                fields[key] = _s(entry.get("value"))
        return Body(type="multipart", content=fields), None
    if mode in (None, "none"):
        return Body(), None
    report.skipped.append(f"{label}: body '{mode}' no soportado")
    return Body(), None


def _request(item: dict[str, Any], name: str, report: ImportReport, label: str) -> Request | None:
    raw = item["request"]
    if isinstance(raw, str):
        raw = {"url": raw}
    if not isinstance(raw, dict):
        report.skipped.append(f"{label}: request inválido")
        return None
    method = _s(raw.get("method") or "GET").upper()
    if method not in METHODS:
        report.skipped.append(f"{label}: método {method} no soportado")
        return None
    url, params = _url(raw.get("url"))
    headers = _pairs(raw.get("header"))
    body, content_type = _body(raw.get("body"), report, label)
    if content_type and not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = content_type
    _note_events(item, report, label)
    auth = _auth(raw.get("auth"), report, label)
    return Request(
        name=name,
        description=_description(raw.get("description")),
        method=cast(HttpMethod, method),
        url=url,
        params=params,
        headers=headers,
        body=body,
        auth=auth or AuthInherit(),
    )


def _import_items(items: list[Any], directory: Path, report: ImportReport, trail: str) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _s(item.get("name")) or "sin-nombre"
        label = f"{trail}/{name}"
        if isinstance(item.get("item"), list):
            folder_dir = unique_path(directory, name)
            folder_dir.mkdir(parents=True)
            _note_events(item, report, label)
            write_json(
                folder_dir / FOLDER_FILE,
                FolderMeta(
                    name=name,
                    description=_description(item.get("description")),
                    auth=_auth(item.get("auth"), report, label),
                    variables=_variables(item.get("variable")),
                ),
            )
            report.folders += 1
            _import_items(item["item"], folder_dir, report, label)
        elif "request" in item:
            request = _request(item, name, report, label)
            if request is not None:
                write_json(unique_path(directory, name, ".json"), request)
                report.requests += 1
        else:
            report.skipped.append(f"{label}: ítem sin request ni carpeta")


def import_collection(data: Any, root: Path, group: str) -> ImportReport:
    with _import_errors():
        return _import_collection(data, root, group)


def import_environment(data: Any, root: Path) -> ImportReport:
    with _import_errors():
        return _import_environment(data, root)


@contextmanager
def _import_errors() -> Iterator[None]:
    """Convierte formatos inesperados y fallos de secrets.json en PostmanImportError."""
    try:
        yield
    except SecretsError as exc:
        raise PostmanImportError(str(exc)) from exc
    except (AttributeError, TypeError, KeyError, ValueError) as exc:
        raise PostmanImportError(f"formato Postman no reconocido: {exc}") from exc


def _import_collection(data: Any, root: Path, group: str) -> ImportReport:
    if not isinstance(data, dict) or not isinstance(data.get("item"), list):
        raise PostmanImportError("el archivo no parece una colección Postman (falta 'item')")
    info = data.get("info") or {}
    schema = _s(info.get("schema"))
    if schema and "v2.0" not in schema and "v2.1" not in schema:
        raise PostmanImportError(f"versión de colección no soportada: {schema}")
    report = ImportReport()
    group_dir = root / GROUPS_DIR / slugify(group)
    if not (group_dir / GROUP_FILE).exists():
        write_json(group_dir / GROUP_FILE, GroupMeta(name=group))
    name = _s(info.get("name")) or "coleccion"
    col_dir = unique_path(group_dir, name)
    col_dir.mkdir(parents=True)
    _note_events(data, report, name)
    write_json(
        col_dir / COLLECTION_FILE,
        CollectionMeta(
            name=name,
            description=_description(info.get("description")),
            auth=_auth(data.get("auth"), report, name),
            variables=_variables(data.get("variable")),
        ),
    )
    _import_items(data["item"], col_dir, report, name)
    report.target = col_dir
    return report


def _import_environment(data: Any, root: Path) -> ImportReport:
    if not is_environment(data) or not isinstance(data["values"], list):
        raise PostmanImportError("el archivo no parece un entorno Postman (falta 'values')")
    name = _s(data.get("name")) or "entorno"
    path = root / ENVIRONMENTS_DIR / f"{slugify(name)}.json"
    if path.exists():
        raise PostmanImportError(f"ya existe el entorno '{name}' en {path}")
    variables: dict[str, str | SecretRef] = {}
    env_secrets: dict[str, str] = {}
    for entry in data["values"]:
        if not isinstance(entry, dict) or not entry.get("key") or entry.get("enabled") is False:
            continue
        key = str(entry["key"])
        value = _s(entry.get("value"))
        if entry.get("type") == "secret":
            variables[key] = SecretRef(secret=True)
            env_secrets[key] = value
        else:
            variables[key] = value
    write_json(path, Environment(name=name, variables=variables))
    if env_secrets:
        secrets = load_secrets(root)
        secrets[name] = {**secrets.get(name, {}), **env_secrets}
        save_secrets(root, secrets)
    return ImportReport(target=path, environments=1)


def format_report(report: ImportReport) -> str:
    lines: list[str] = []
    if report.target:
        lines.append(f"Destino: {report.target}")
    if report.environments:
        lines.append(f"{report.environments} entorno(s) importado(s)")
    else:
        lines.append(f"{report.requests} requests importados en {report.folders} carpetas")
    if report.skipped:
        lines.append(f"Omitidos ({len(report.skipped)}):")
        lines += [f"  - {item}" for item in report.skipped]
    return "\n".join(lines)
