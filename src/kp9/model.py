"""Modelos del dominio de kp9 (archivos JSON del workspace)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AuthInherit(_Base):
    type: Literal["inherit"] = "inherit"


class AuthNone(_Base):
    type: Literal["none"] = "none"


class AuthBearer(_Base):
    type: Literal["bearer"] = "bearer"
    token: str


class AuthBasic(_Base):
    type: Literal["basic"] = "basic"
    username: str
    password: str


class AuthApiKey(_Base):
    type: Literal["apikey"] = "apikey"
    key: str
    value: str
    in_: Literal["header", "query"] = Field(default="header", alias="in")


class AuthOAuth2CC(_Base):
    type: Literal["oauth2-cc"] = "oauth2-cc"
    tokenUrl: str
    clientId: str
    clientSecret: str
    scopes: list[str] = Field(default_factory=list)


Auth = Annotated[
    AuthInherit | AuthNone | AuthBearer | AuthBasic | AuthApiKey | AuthOAuth2CC,
    Field(discriminator="type"),
]

BodyType = Literal["none", "json", "text", "form-urlencoded", "multipart"]
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class Body(_Base):
    type: BodyType = "none"
    content: Any = None


class Request(_Base):
    name: str
    description: str = ""
    method: HttpMethod = "GET"
    url: str
    params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Body = Field(default_factory=Body)
    auth: Auth = Field(default_factory=AuthInherit)


class NodeMeta(_Base):
    name: str
    description: str = ""
    auth: Auth | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class GroupMeta(NodeMeta):
    pass


class CollectionMeta(NodeMeta):
    baseUrl: str | None = None


class FolderMeta(NodeMeta):
    pass


class SecretRef(_Base):
    secret: Literal[True]


class Environment(_Base):
    name: str
    description: str = ""
    protected: bool = False
    variables: dict[str, str | SecretRef] = Field(default_factory=dict)


class WorkspaceConfig(_Base):
    name: str
    description: str = ""
    defaultGroup: str | None = None
    defaultEnv: str | None = None
    timeout: float = 30.0
    redactHeaders: list[str] = Field(default_factory=list)


def dump(model: BaseModel) -> dict[str, Any]:
    """Serializa un modelo tal como se escribe en disco."""
    return model.model_dump(by_alias=True, exclude_none=True, mode="json")
