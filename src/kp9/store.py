"""Carga y escritura del workspace kp9 en disco."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from kp9.model import (
    CollectionMeta,
    Environment,
    FolderMeta,
    GroupMeta,
    NodeMeta,
    Request,
    WorkspaceConfig,
    dump,
)

WORKSPACE_FILE = "workspace.json"
LOCAL_DIR = ".kp9"
ENVIRONMENTS_DIR = "environments"
GROUPS_DIR = "groups"
GROUP_FILE = "group.json"
COLLECTION_FILE = "collection.json"
FOLDER_FILE = "folder.json"
META_FILES = frozenset({GROUP_FILE, COLLECTION_FILE, FOLDER_FILE})

Kind = Literal["group", "collection", "folder"]
_META: dict[Kind, tuple[str, type[NodeMeta]]] = {
    "group": (GROUP_FILE, GroupMeta),
    "collection": (COLLECTION_FILE, CollectionMeta),
    "folder": (FOLDER_FILE, FolderMeta),
}
_CHILD_KIND: dict[Kind, Kind] = {"group": "collection", "collection": "folder", "folder": "folder"}
_META_MODELS: dict[str, type[BaseModel]] = {
    GROUP_FILE: GroupMeta,
    COLLECTION_FILE: CollectionMeta,
    FOLDER_FILE: FolderMeta,
}

M = TypeVar("M", bound=BaseModel)


class WorkspaceNotFound(Exception):
    """No hay un workspace.json válido."""


@dataclass
class RequestNode:
    path: Path
    request: Request | None
    error: str | None
    chain: list[NodeMeta]

    @property
    def name(self) -> str:
        return self.request.name if self.request else self.path.stem


@dataclass
class ContainerNode:
    kind: Kind
    path: Path
    meta: NodeMeta | None
    error: str | None
    children: list[ContainerNode] = field(default_factory=list)
    requests: list[RequestNode] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.meta.name if self.meta else self.path.name

    @property
    def meta_file(self) -> Path:
        return self.path / _META[self.kind][0]


@dataclass
class Workspace:
    root: Path
    config: WorkspaceConfig
    groups: list[ContainerNode] = field(default_factory=list)
    environments: dict[str, Environment] = field(default_factory=dict)
    env_files: dict[str, Path] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    index: dict[Path, ContainerNode | RequestNode] = field(default_factory=dict)

    def node_at(self, path: Path) -> ContainerNode | RequestNode | None:
        return self.index.get(path)


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "item"


def unique_path(directory: Path, name: str, suffix: str = "") -> Path:
    """Ruta libre `<slug><suffix>`; nunca devuelve un archivo meta ni uno existente."""
    base = slugify(name)
    candidate = directory / f"{base}{suffix}"
    n = 2
    while candidate.exists() or candidate.name in META_FILES:
        candidate = directory / f"{base}-{n}{suffix}"
        n += 1
    return candidate


def read_model(path: Path, cls: type[M]) -> tuple[M | None, str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path}: {exc.strerror}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"{path}:{exc.lineno}:{exc.colno}: {exc.msg}"
    try:
        return cls.model_validate(data), None
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"]) or "<raíz>"
        return None, f"{path}: {loc}: {first['msg']}"


def write_json(path: Path, data: BaseModel | dict[str, Any]) -> None:
    payload = dump(data) if isinstance(data, BaseModel) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_workspace(root: Path) -> Workspace:
    root = root.resolve()
    config, error = read_model(root / WORKSPACE_FILE, WorkspaceConfig)
    if config is None:
        raise WorkspaceNotFound(error or f"{root / WORKSPACE_FILE}: inválido")
    ws = Workspace(root=root, config=config)
    env_dir = root / ENVIRONMENTS_DIR
    if env_dir.is_dir():
        for path in sorted(env_dir.glob("*.json")):
            env, env_error = read_model(path, Environment)
            if env is None:
                ws.errors.append(env_error or str(path))
                continue
            ws.environments[env.name] = env
            ws.env_files[env.name] = path
    groups_dir = root / GROUPS_DIR
    if groups_dir.is_dir():
        for directory in sorted(p for p in groups_dir.iterdir() if p.is_dir()):
            if not directory.name.startswith("."):
                ws.groups.append(_load_container(ws, directory, "group", []))
    return ws


def _load_container(
    ws: Workspace, directory: Path, kind: Kind, chain: list[NodeMeta]
) -> ContainerNode:
    filename, cls = _META[kind]
    meta_path = directory / filename
    meta: NodeMeta | None
    error: str | None
    if meta_path.exists():
        meta, error = read_model(meta_path, cls)
    elif kind == "folder":
        meta, error = FolderMeta(name=directory.name), None
    else:
        meta, error = None, f"{meta_path}: archivo faltante"
    if error:
        ws.errors.append(error)
    node = ContainerNode(kind=kind, path=directory, meta=meta, error=error)
    sub_chain = chain + ([meta] if meta else [])
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_dir():
            node.children.append(_load_container(ws, path, _CHILD_KIND[kind], sub_chain))
        elif path.suffix == ".json" and path.name not in META_FILES and kind != "group":
            request, req_error = read_model(path, Request)
            if req_error:
                ws.errors.append(req_error)
            request_node = RequestNode(path=path, request=request, error=req_error, chain=sub_chain)
            node.requests.append(request_node)
            ws.index[path] = request_node
    ws.index[directory] = node
    return node


def init_workspace(root: Path, name: str) -> Path:
    root = root.resolve()
    config_path = root / WORKSPACE_FILE
    if config_path.exists():
        raise FileExistsError(f"ya existe un workspace en {root}")
    for sub in (ENVIRONMENTS_DIR, GROUPS_DIR, LOCAL_DIR):
        (root / sub).mkdir(parents=True, exist_ok=True)
    write_json(config_path, WorkspaceConfig(name=name))
    gitignore = root / ".gitignore"
    entry = f"{LOCAL_DIR}/"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if entry not in lines:
        lines.append(entry)
        gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def find_workspace_root(start: Path) -> Path:
    start = start.resolve()
    for directory in (start, *start.parents):
        if (directory / WORKSPACE_FILE).is_file():
            return directory
    raise WorkspaceNotFound(
        f"No se encontró {WORKSPACE_FILE} en {start} ni en sus carpetas padre. "
        "Crea uno con `kp9 init`."
    )


def count_requests(node: ContainerNode) -> int:
    return len(node.requests) + sum(count_requests(child) for child in node.children)


def group_dir_of(root: Path, path: Path) -> Path | None:
    groups = root / GROUPS_DIR
    try:
        rel = path.relative_to(groups)
    except ValueError:
        return None
    return groups / rel.parts[0] if rel.parts else None


def model_for_file(root: Path, path: Path) -> type[BaseModel]:
    if path == root / WORKSPACE_FILE:
        return WorkspaceConfig
    if path.parent == root / ENVIRONMENTS_DIR:
        return Environment
    if path.name in _META_MODELS:
        return _META_MODELS[path.name]
    return Request
