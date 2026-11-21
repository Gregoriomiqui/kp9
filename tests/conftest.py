import json
from pathlib import Path
from typing import Any

import pytest


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def write_file():
    return write


@pytest.fixture
def sample_ws(tmp_path: Path) -> Path:
    root = (tmp_path / "mis-apis").resolve()
    write(root / "workspace.json", {"name": "mis-apis", "defaultEnv": "qa"})
    write(
        root / "environments" / "qa.json",
        {
            "name": "qa",
            "variables": {
                "baseUrl": "https://qa.example.com",
                "token": {"secret": True},
                "sku": "SKU-1",
            },
        },
    )
    write(
        root / "environments" / "prod.json",
        {
            "name": "prod",
            "protected": True,
            "variables": {
                "baseUrl": "https://api.example.com",
                "token": {"secret": True},
                "sku": "SKU-PROD",
            },
        },
    )
    write(
        root / ".kp9" / "secrets.json",
        {"qa": {"token": "qa-secret-token"}, "prod": {"token": "prod-secret-token"}},
    )
    group = root / "groups" / "pagos"
    write(group / "group.json", {"name": "Pagos", "auth": {"type": "bearer", "token": "{{token}}"}})
    col = group / "checkout-api"
    write(col / "collection.json", {"name": "Checkout API", "variables": {"apiVersion": "v1"}})
    write(
        col / "carrito" / "agregar-al-carrito.json",
        {
            "name": "Agregar al carrito",
            "method": "POST",
            "url": "{{baseUrl}}/{{apiVersion}}/cart/items",
            "headers": {"Content-Type": "application/json"},
            "body": {"type": "json", "content": {"sku": "{{sku}}", "qty": 1}},
        },
    )
    write(
        col / "carrito" / "ver-carrito.json",
        {"name": "Ver carrito", "url": "{{baseUrl}}/{{apiVersion}}/cart"},
    )
    write(
        col / "buscar.json",
        {
            "name": "Buscar",
            "url": "{{baseUrl}}/{{apiVersion}}/search",
            "params": {"q": "{{query}}"},
        },
    )
    return root


from collections.abc import Callable  # noqa: E402

import httpx  # noqa: E402


class Recorder:
    """Handler para httpx.MockTransport que guarda los requests recibidos."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responder: Callable[[httpx.Request], httpx.Response] = lambda request: httpx.Response(
            200, json={"ok": True, "items": [1, 2]}
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responder(request)


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()
