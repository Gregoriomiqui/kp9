import json

import pytest

from kp9.model import CollectionMeta, Environment, FolderMeta, GroupMeta, Request, WorkspaceConfig
from kp9.store import (
    ContainerNode,
    RequestNode,
    WorkspaceNotFound,
    count_requests,
    find_workspace_root,
    group_dir_of,
    init_workspace,
    load_workspace,
    model_for_file,
    read_model,
    slugify,
    unique_path,
    write_json,
)

CARRITO = "groups/pagos/checkout-api/carrito"


def test_slugify_handles_accents_and_symbols():
    assert slugify("Agregar al Carrito ñ!") == "agregar-al-carrito-n"
    assert slugify("   ") == "item"


def test_unique_path_appends_suffix_on_collision(tmp_path):
    (tmp_path / "ver.json").write_text("{}")
    assert unique_path(tmp_path, "Ver", ".json").name == "ver-2.json"
    (tmp_path / "ver-2.json").write_text("{}")
    assert unique_path(tmp_path, "Ver", ".json").name == "ver-3.json"


def test_unique_path_never_returns_meta_file_name(tmp_path):
    assert unique_path(tmp_path, "Folder", ".json").name == "folder-2.json"
    assert unique_path(tmp_path, "Collection", ".json").name == "collection-2.json"
    assert unique_path(tmp_path, "Group", ".json").name == "group-2.json"


def test_load_workspace_builds_tree(sample_ws):
    ws = load_workspace(sample_ws)
    assert ws.config.name == "mis-apis"
    assert sorted(ws.environments) == ["prod", "qa"]
    assert ws.env_files["qa"] == sample_ws / "environments" / "qa.json"
    [group] = ws.groups
    assert (group.kind, group.name) == ("group", "Pagos")
    [col] = group.children
    assert (col.kind, col.name) == ("collection", "Checkout API")
    assert [r.name for r in col.requests] == ["Buscar"]
    [folder] = col.children
    assert (folder.kind, folder.name) == ("folder", "carrito")
    assert [r.name for r in folder.requests] == ["Agregar al carrito", "Ver carrito"]
    assert count_requests(col) == 3
    assert ws.errors == []


def test_request_chain_is_outermost_first(sample_ws):
    ws = load_workspace(sample_ws)
    node = ws.node_at(sample_ws / CARRITO / "ver-carrito.json")
    assert isinstance(node, RequestNode)
    assert [m.name for m in node.chain] == ["Pagos", "Checkout API", "carrito"]


def test_index_contains_containers(sample_ws):
    ws = load_workspace(sample_ws)
    node = ws.node_at(sample_ws / CARRITO)
    assert isinstance(node, ContainerNode)
    assert node.meta_file == sample_ws / CARRITO / "folder.json"


def test_invalid_json_marks_only_that_request(sample_ws):
    bad = sample_ws / CARRITO / "roto.json"
    bad.write_text('{\n  "name": "Roto",\n  "url": \n}')
    ws = load_workspace(sample_ws)
    node = ws.node_at(bad)
    assert isinstance(node, RequestNode)
    assert node.request is None
    assert node.error == f"{bad}:4:1: Expecting value"
    assert node.name == "roto"
    folder = ws.node_at(sample_ws / CARRITO)
    assert len(folder.requests) == 3
    assert ws.errors == [node.error]


def test_validation_error_reports_field_path(sample_ws):
    bad = sample_ws / CARRITO / "sin-url.json"
    bad.write_text(json.dumps({"name": "x"}))
    node = load_workspace(sample_ws).node_at(bad)
    assert node.error == f"{bad}: url: Field required"


def test_invalid_group_meta_marks_group(sample_ws):
    (sample_ws / "groups/pagos/group.json").write_text("[]")
    [group] = load_workspace(sample_ws).groups
    assert group.meta is None
    assert group.error is not None
    assert group.name == "pagos"


def test_missing_optional_dirs_ok(tmp_path, write_file):
    write_file(tmp_path / "workspace.json", {"name": "w"})
    ws = load_workspace(tmp_path)
    assert ws.groups == []
    assert ws.environments == {}


def test_missing_workspace_raises(tmp_path):
    with pytest.raises(WorkspaceNotFound):
        load_workspace(tmp_path)


def test_find_workspace_root_walks_up(sample_ws, tmp_path):
    assert find_workspace_root(sample_ws / "groups" / "pagos") == sample_ws
    with pytest.raises(WorkspaceNotFound, match="kp9 init"):
        find_workspace_root(tmp_path)


def test_init_workspace_creates_structure_and_gitignore(tmp_path):
    root = init_workspace(tmp_path / "w", "mis-apis")
    assert json.loads((root / "workspace.json").read_text())["name"] == "mis-apis"
    assert (root / "environments").is_dir()
    assert (root / "groups").is_dir()
    assert (root / ".kp9").is_dir()
    assert (root / ".gitignore").read_text() == ".kp9/\n"
    with pytest.raises(FileExistsError):
        init_workspace(root, "otra")


def test_init_appends_to_existing_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    init_workspace(tmp_path, "w")
    assert (tmp_path / ".gitignore").read_text().splitlines() == ["node_modules/", ".kp9/"]


def test_write_json_roundtrip(tmp_path):
    path = tmp_path / "a" / "r.json"
    write_json(path, Request(name="x", url="u"))
    model, err = read_model(path, Request)
    assert err is None
    assert model is not None and model.name == "x"
    assert path.read_text().endswith("}\n")


def test_group_dir_of(sample_ws):
    assert group_dir_of(sample_ws, sample_ws / CARRITO / "ver-carrito.json") == (
        sample_ws / "groups" / "pagos"
    )
    assert group_dir_of(sample_ws, sample_ws / "environments" / "qa.json") is None


def test_model_for_file(sample_ws):
    assert model_for_file(sample_ws, sample_ws / "workspace.json") is WorkspaceConfig
    assert model_for_file(sample_ws, sample_ws / "environments/qa.json") is Environment
    assert model_for_file(sample_ws, sample_ws / "groups/pagos/group.json") is GroupMeta
    assert model_for_file(sample_ws, sample_ws / "groups/pagos/checkout-api/collection.json") is (
        CollectionMeta
    )
    assert model_for_file(sample_ws, sample_ws / CARRITO / "folder.json") is FolderMeta
    assert model_for_file(sample_ws, sample_ws / CARRITO / "ver-carrito.json") is Request
