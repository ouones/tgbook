"""Immutable configuration, result, and output dataclasses."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Resolved application configuration."""

    bot_username: str
    phone: str
    api_id: int
    api_hash: str
    config_path: Path | None
    data_root: Path

    @property
    def session_path(self) -> Path:
        return self.data_root / "session" / f"{self.phone}.session"

    @property
    def lock_path(self) -> Path:
        return self.data_root / "locks" / f"{self.phone}.lock"

    @property
    def download_index_path(self) -> Path:
        return self.data_root / "download-index.json"


@dataclass(frozen=True)
class BookResult:
    """A single book search result parsed from the bot's response."""

    command: str
    title: str | None = None
    author: str | None = None
    format: str | None = None
    size: str | None = None

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "title": self.title,
            "author": self.author,
            "format": self.format,
            "size": self.size,
        }


@dataclass(frozen=True)
class DownloadedFile:
    """Result of a successful or skipped download."""

    path: Path
    filename: str
    format: str | None = None
    size: int | None = None
    skipped: bool = False


@dataclass(frozen=True)
class ButtonRef:
    """Reference to an inline keyboard button by position."""

    row: int
    column: int


@dataclass
class IncomingMessage:
    """A message received from Telegram, used by both real and fake gateways."""

    id: int
    chat_id: int
    sender_id: int
    text: str | None = None
    buttons: list[list[tuple[str, str]]] | None = None  # [[(callback_data, text)]]
    document: tuple[str, bytes] | None = None  # (filename, content) — bytes only in fake


class BotGateway(ABC):
    """Abstract gateway for bot communication — real Kurigram or fake for tests."""

    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
    @abstractmethod
    async def send_text(self, text: str) -> int: ...
    @abstractmethod
    async def messages_after(self, after_id: int) -> list[IncomingMessage]: ...
    @abstractmethod
    async def get_message(self, message_id: int) -> IncomingMessage | None: ...
    @abstractmethod
    async def click(self, message_id: int, row: int, column: int) -> None: ...
    @abstractmethod
    async def download_document(self, message: IncomingMessage, dest: Path) -> Path: ...

    @property
    @abstractmethod
    def bot_chat_id(self) -> int: ...
    @property
    @abstractmethod
    def bot_user_id(self) -> int: ...
