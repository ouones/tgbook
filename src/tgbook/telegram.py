"""Kurigram client lifecycle and private-chat transport adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError

from tgbook.errors import ErrorCode, TgbookError
from tgbook.models import AppConfig, BotGateway, IncomingMessage


class KurigramGateway(BotGateway):
    """Real Telegram gateway backed by a Kurigram client.

    Manages one session file, resolves the configured bot into a private chat,
    and filters all incoming messages to only that bot in that chat.
    """

    def __init__(self, config: AppConfig, interactive: bool) -> None:
        self._config = config
        self._interactive = interactive
        self._client: Client | None = None
        self._bot_chat_id: int | None = None
        self._bot_user_id: int | None = None

    @property
    def bot_chat_id(self) -> int:
        if self._bot_chat_id is None:
            raise TgbookError(ErrorCode.INTERNAL_ERROR, "Gateway not started.")
        return self._bot_chat_id

    @property
    def bot_user_id(self) -> int:
        if self._bot_user_id is None:
            raise TgbookError(ErrorCode.INTERNAL_ERROR, "Gateway not started.")
        return self._bot_user_id

    async def start(self) -> None:
        if not self._interactive and not self._config.session_path.is_file():
            raise TgbookError(
                ErrorCode.LOGIN_REQUIRED,
                "No session file found. Run 'tgbook login' interactively first.",
            )

        # Ensure session directory exists
        self._config.session_path.parent.mkdir(parents=True, exist_ok=True)

        self._client = Client(
            name=self._config.phone,
            api_id=self._config.api_id,
            api_hash=self._config.api_hash,
            phone_number=self._config.phone,
            workdir=str(self._config.session_path.parent),
            no_updates=True,
            proxy=self._make_proxy(),
        )

        try:
            await self._client.start()
        except RPCError as exc:
            raise self._map_error(exc)

        # Resolve the bot
        try:
            bot = await self._client.get_users(self._config.bot_username)
        except RPCError as exc:
            raise self._map_error(exc)

        if bot.is_bot is not True:
            raise TgbookError(
                ErrorCode.PROTOCOL_ERROR,
                f"@{self._config.bot_username} is not a Telegram bot.",
            )

        self._bot_user_id = bot.id
        self._bot_chat_id = bot.id  # private chat: chat_id == user_id

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.stop()

    async def send_text(self, text: str) -> int:
        assert self._client is not None
        try:
            message = await self._client.send_message(self.bot_chat_id, text)
            return message.id
        except FloodWait as exc:
            raise TgbookError(
                ErrorCode.RATE_LIMITED,
                f"Rate limited: wait {exc.value} seconds.",
                retry_after=exc.value,
            )
        except RPCError as exc:
            raise self._map_error(exc)

    async def messages_after(self, after_id: int) -> list[IncomingMessage]:
        assert self._client is not None
        try:
            messages = []
            async for msg in self._client.get_chat_history(self.bot_chat_id, limit=20):
                if msg.id <= after_id:
                    break
                if msg.from_user and msg.from_user.id == self.bot_user_id:
                    messages.append(self._convert(msg))
            return list(reversed(messages))
        except RPCError as exc:
            raise self._map_error(exc)

    async def get_message(self, message_id: int) -> IncomingMessage | None:
        assert self._client is not None
        try:
            msg = await self._client.get_messages(self.bot_chat_id, message_ids=message_id)
            if msg is None:
                return None
            return self._convert(msg)
        except RPCError as exc:
            raise self._map_error(exc)

    async def click(self, message_id: int, row: int, column: int) -> None:
        assert self._client is not None
        try:
            message = await self._client.get_messages(self.bot_chat_id, message_ids=message_id)
            if message is None or not message.reply_markup:
                raise TgbookError(
                    ErrorCode.PROTOCOL_ERROR,
                    "No inline keyboard found on the target message.",
                )
            await message.click(row)
        except FloodWait as exc:
            raise TgbookError(
                ErrorCode.RATE_LIMITED,
                f"Rate limited: wait {exc.value} seconds.",
                retry_after=exc.value,
            )
        except RPCError as exc:
            raise self._map_error(exc)

    async def download_document(self, message: IncomingMessage, dest: Path) -> Path:
        # For the real gateway, we download from the actual Telegram message
        # The IncomingMessage carries the raw pyrogram message reference
        assert self._client is not None
        try:
            tg_msg = await self._client.get_messages(self.bot_chat_id, message_ids=message.id)
            if tg_msg is None or tg_msg.document is None:
                raise TgbookError(
                    ErrorCode.DOWNLOAD_FAILED,
                    "No document found in the message.",
                )
            await tg_msg.download(file_name=str(dest))
            return dest
        except RPCError as exc:
            raise self._map_error(exc)

    def _make_proxy(self) -> dict | None:
        """Build a pyrogram proxy dict from the config proxy string.

        Supports socks5:// and http:// schemes. Defaults to socks5.
        Examples: 'socks5://192.168.31.2:7890', 'http://127.0.0.1:8080'
        """
        proxy_url = self._config.proxy
        if not proxy_url:
            return None
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        scheme = parsed.scheme or "socks5"
        hostname = parsed.hostname
        port = parsed.port
        if not hostname or not port:
            return None
        return {
            "scheme": scheme,
            "hostname": hostname,
            "port": port,
            **({"username": parsed.username, "password": parsed.password}
               if parsed.username and parsed.password else {}),
        }

    def _convert(self, msg) -> IncomingMessage:
        buttons = None
        if msg.reply_markup and hasattr(msg.reply_markup, 'inline_keyboard'):
            buttons = [
                [(btn.callback_data or "", btn.text or "") for btn in row]
                for row in msg.reply_markup.inline_keyboard
            ]

        document = None
        if msg.document:
            document = (msg.document.file_name or "unknown", b"")  # real content via download_document

        return IncomingMessage(
            id=msg.id,
            chat_id=msg.chat.id,
            sender_id=msg.from_user.id if msg.from_user else 0,
            text=msg.text or msg.caption,
            buttons=buttons,
            document=document,
        )

    def _map_error(self, exc: RPCError) -> TgbookError:
        if isinstance(exc, FloodWait):
            return TgbookError(
                ErrorCode.RATE_LIMITED,
                f"Rate limited: wait {exc.value} seconds.",
                retry_after=exc.value,
            )
        error_msg = str(exc)
        if "AUTH_KEY" in error_msg.upper() or "UNAUTHORIZED" in error_msg.upper() or "SESSION" in error_msg.upper():
            return TgbookError(
                ErrorCode.LOGIN_REQUIRED,
                "Session is invalid. Run 'tgbook login' interactively.",
            )
        return TgbookError(ErrorCode.TELEGRAM_ERROR, error_msg)
