from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field


class SessionKind(str, Enum):
    PYROGRAM = "PYROGRAM"
    TELETHON = "TELETHON"
    UNKNOWN = "UNKNOWN"


class SessionStatus(str, Enum):
    UNKNOWN = "unknown"
    VALID = "valid"
    INVALID = "invalid"
    CHECKING = "checking"


class SessionInfo(BaseModel):
    name: str
    phone: str = ""
    first_name: str = ""
    last_name: str = ""
    username: str = ""
    bio: str = ""
    kind: SessionKind = SessionKind.PYROGRAM
    status: SessionStatus = SessionStatus.UNKNOWN

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.name


class ParsedUser(BaseModel):
    id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    avatar_path: str = ""
    bio: str = ""
    song: str = ""
    birthday: str = ""
    gifts: list[dict[str, Any]] = Field(default_factory=list)
    source_chat_id: int | None = None
    source_chat_title: str = ""
    source_chat_username: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip() or str(self.id)
        tag = f" (@{self.username})" if self.username else ""
        return f"{name}{tag}"


class SendResult(BaseModel):
    session: str
    target: str
    success: bool
    error: str = ""


class ProfileSnapshot(BaseModel):
    timestamp: str
    id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    bio: str = ""
