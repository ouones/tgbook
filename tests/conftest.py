"""Shared test fixtures: fake transport and temporary configuration helpers."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tgbook.models import BotGateway, IncomingMessage


@dataclass
class QueuedMessage:
    text: str | None = None
    document: tuple[str, bytes] | None = None  # (filename, content)
    buttons: list[list[tuple[str, str]]] | None = None  # [[(callback, text)]]


@dataclass
class FakeGateway(BotGateway):
    """Simulated private-chat gateway, no Telegram credentials needed.

    Two separate queues:
    - _send_queue: consumed by send_text (search pages, text info, documents)
    - _click_queue: consumed by click (message edits after pagination)
    """

    bot_chat_id: int = 123456
    bot_user_id: int = 789012
    sent_text: list[str] = field(default_factory=list)
    clicked: list[tuple[int, int, int]] = field(default_factory=list)  # [(msg_id, row, col)]
    message_counter: int = field(default_factory=lambda: 1)
    _send_queue: list[QueuedMessage] = field(default_factory=list)
    _click_queue: list[QueuedMessage] = field(default_factory=list)
    _messages: dict[int, IncomingMessage] = field(default_factory=dict)
    _edits: dict[int, list[IncomingMessage]] = field(default_factory=dict)
    _downloaded: list[tuple[str, bytes]] = field(default_factory=list)  # [(filename, content)]

    def queue_search_page(self, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> int:
        """Queue a text response with optional inline buttons, return the message ID."""
        msg = QueuedMessage(text=text, buttons=buttons)
        self._send_queue.append(msg)
        return len(self._send_queue)

    def queue_edit(self, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
        """Queue a message edit to be consumed by click()."""
        msg = QueuedMessage(text=text, buttons=buttons)
        self._click_queue.append(msg)

    def queue_text(self, text: str) -> None:
        self._send_queue.append(QueuedMessage(text=text))

    def queue_document(self, filename: str, content: bytes) -> None:
        self._send_queue.append(QueuedMessage(document=(filename, content)))

    # -- BotGateway implementation --

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_text(self, text: str) -> int:
        self.sent_text.append(text)
        msg_id = self.message_counter
        self.message_counter += 1
        # Dequeue ALL send-queued responses (bot may send multiple messages per command)
        while self._send_queue:
            queued = self._send_queue.pop(0)
            incoming = IncomingMessage(
                id=self.message_counter,
                chat_id=self.bot_chat_id,
                sender_id=self.bot_user_id,
                text=queued.text,
                buttons=queued.buttons,
                document=queued.document,
            )
            self._messages[incoming.id] = incoming
            self.message_counter += 1
        return msg_id

    async def messages_after(self, after_id: int) -> list[IncomingMessage]:
        return [m for mid, m in self._messages.items() if mid > after_id]

    async def get_message(self, message_id: int) -> IncomingMessage | None:
        # Check edits first (most recent edit)
        if message_id in self._edits and self._edits[message_id]:
            return self._edits[message_id][-1]
        return self._messages.get(message_id)

    async def click(self, message_id: int, row: int, column: int) -> None:
        self.clicked.append((message_id, row, column))
        # Dequeue the next click-queued response (typically a page edit)
        if self._click_queue:
            queued = self._click_queue.pop(0)
            incoming = IncomingMessage(
                id=message_id,
                chat_id=self.bot_chat_id,
                sender_id=self.bot_user_id,
                text=queued.text,
                buttons=queued.buttons,
            )
            self._edits.setdefault(message_id, []).append(incoming)

    async def download_document(self, message: IncomingMessage, dest: Path) -> Path:
        if message.document:
            self._downloaded.append(message.document)
            dest.write_bytes(message.document[1])
        return dest


@pytest.fixture
def fake_gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def load_fixture():
    def _load(name: str) -> str:
        fixture_path = Path(__file__).parent / "fixtures" / name
        return fixture_path.read_text(encoding="utf-8")
    return _load
