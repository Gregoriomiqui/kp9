"""Orquestación de un envío: resolver → autenticar → enviar → registrar."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

from kp9.auth import AuthError, TokenCache, apply_auth
from kp9.history import History
from kp9.httpclient import RequestFailed, Response, send
from kp9.model import Environment
from kp9.redact import Redactor
from kp9.resolve import ResolvedRequest, resolve
from kp9.secrets import SecretsError, env_values, load_secrets, sensitive_values
from kp9.store import RequestNode, Workspace
from kp9.variables import VariableInfo, available_variables

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CANCELLED = "cancelado"


class NotSendable(Exception):
    """El request no puede prepararse (archivo inválido, secrets.json roto)."""


@dataclass(frozen=True)
class SendOutcome:
    resolved: ResolvedRequest
    response: Response | None
    error: str | None
    history_id: int


class Runner:
    def __init__(
        self,
        workspace: Workspace,
        history: History,
        client: httpx.AsyncClient,
        cache: TokenCache | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.workspace = workspace
        self.history = history
        self.client = client
        self.cache = cache or TokenCache()
        self._environ: Mapping[str, str] = os.environ if environ is None else environ

    def environment(self, env_name: str | None) -> Environment | None:
        return self.workspace.environments.get(env_name) if env_name else None

    def _values(self, env_name: str | None) -> tuple[dict[str, str], list[str]]:
        env = self.environment(env_name)
        try:
            secrets = load_secrets(self.workspace.root)
        except SecretsError as exc:
            raise NotSendable(str(exc)) from exc
        return (
            env_values(env, secrets, self._environ),
            sensitive_values(env, secrets, self._environ),
        )

    def redactor(self, env_name: str | None) -> Redactor:
        _, sensitive = self._values(env_name)
        return Redactor(sensitive, self.workspace.config.redactHeaders)

    def variables_for(self, node: RequestNode, env_name: str | None) -> list[VariableInfo]:
        """Variables disponibles para el request (para autocompletar). Nunca falla."""
        try:
            secrets = load_secrets(self.workspace.root)
        except SecretsError:
            secrets = {}
        return available_variables(node.chain, self.environment(env_name), secrets, self._environ)

    def prepare(self, node: RequestNode, env_name: str | None) -> ResolvedRequest:
        if node.request is None:
            raise NotSendable(node.error or f"{node.path}: request inválido")
        values, _ = self._values(env_name)
        return resolve(node.request, node.chain, values, env_name)

    def needs_confirmation(self, resolved: ResolvedRequest, env_name: str | None) -> bool:
        env = self.environment(env_name)
        return bool(env and env.protected and resolved.method not in SAFE_METHODS)

    async def authorize(self, resolved: ResolvedRequest) -> ResolvedRequest:
        return await apply_auth(resolved, self.client, self.cache)

    async def execute(
        self, resolved: ResolvedRequest, env_name: str | None, request_path: Path | None
    ) -> SendOutcome:
        redactor = self.redactor(env_name)
        rel = request_path.relative_to(self.workspace.root).as_posix() if request_path else None
        sent = resolved
        response: Response | None = None
        error: str | None = None
        try:
            sent = await self.authorize(resolved)
            redactor = redactor.with_secrets(_auth_values(resolved, sent))
            response = await send(sent, self.client, self.workspace.config.timeout)
        except AuthError as exc:
            error = f"{exc}\n{exc.body}" if exc.body else str(exc)
        except RequestFailed as exc:
            error = f"{exc.kind}: {exc}"
        except Exception as exc:  # último recurso: nunca tumbar la app ni perder el registro
            error = f"error inesperado: {type(exc).__name__}: {exc}"
        except asyncio.CancelledError:
            self.history.record(
                req=sent,
                response=None,
                error=CANCELLED,
                redactor=redactor,
                env=env_name,
                request_path=rel,
            )
            raise
        safe_error = redactor.text(error) if error else None
        history_id = self.history.record(
            req=sent,
            response=response,
            error=safe_error,
            redactor=redactor,
            env=env_name,
            request_path=rel,
        )
        return SendOutcome(resolved, response, safe_error, history_id)


def _auth_values(before: ResolvedRequest, after: ResolvedRequest) -> list[str]:
    """Valores que agregó la auth (token, Basic en base64, API key) para ocultarlos."""
    values: list[str] = []
    for key, value in after.headers.items():
        if before.headers.get(key) != value:
            values.append(value)
            scheme, _, credential = value.partition(" ")
            if credential:
                values.append(credential)
    values += [v for k, v in after.params.items() if before.params.get(k) != v]
    return values
