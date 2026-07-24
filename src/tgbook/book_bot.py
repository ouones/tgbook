"""Search, pagination, media wait, and atomic download workflow.

Implements the fixed book-bot protocol: send search text, parse /book_xxx results,
click inline pagination buttons, and wait for document media after a /book_xxx command.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from tgbook.errors import ErrorCode, TgbookError
from tgbook.models import BookResult, BotGateway, DownloadedFile, IncomingMessage
from tgbook.parser import find_next_button, parse_search_page


class BookBotService:
    """Operates the fixed book-bot protocol through a gateway."""

    def __init__(self, gateway: BotGateway, deadline_seconds: float = 60.0) -> None:
        self._gateway = gateway
        self._deadline = deadline_seconds

    async def search(self, query: str, page: int = 1) -> list[BookResult]:
        """Search for books and return the requested page of results.

        Sends the query, waits for the bot response, and clicks through
        inline pagination buttons to reach the requested page.
        """
        if page < 1:
            raise TgbookError(ErrorCode.INVALID_INPUT_OR_CONFIG, "Page must be >= 1.")

        # Send the search query
        sent_id = await self._gateway.send_text(query)

        # Wait for the first response with search results
        response = await self._wait_for_message(
            after_id=sent_id,
            predicate=lambda m: m.text is not None and "/book_" in m.text,
        )

        # For page 1, just parse and return
        if page == 1:
            results = parse_search_page(response.text or "")
            if not results:
                raise TgbookError(ErrorCode.NO_RESULTS, "No books found for the query.")
            return results

        # For page > 1, click through pages
        current_page = 1
        current_msg_id = response.id

        while current_page < page:
            # Find the next button
            if not response.buttons:
                raise TgbookError(
                    ErrorCode.PROTOCOL_ERROR,
                    f"No inline keyboard on page {current_page}.",
                )

            button_ref = find_next_button([
                [(cb, txt) for cb, txt in row]
                for row in response.buttons
            ])

            if button_ref is None:
                raise TgbookError(
                    ErrorCode.PROTOCOL_ERROR,
                    f"No next-page button found on page {current_page}.",
                )

            # Click next
            await self._gateway.click(current_msg_id, button_ref.row, button_ref.column)

            # Wait for the edit
            response = await self._wait_for_edit(
                message_id=current_msg_id,
                predicate=lambda m: m.text is not None and "/book_" in m.text,
                previous_text=response.text,
            )
            current_page += 1

        results = parse_search_page(response.text or "")
        if not results:
            raise TgbookError(ErrorCode.NO_RESULTS, f"No results on page {page}.")
        return results

    async def download(self, command: str, output_dir: Path) -> DownloadedFile:
        """Download a book by its /book_xxx command.

        Sends the command to the bot and waits for a document response.
        Writes to a temporary file first, then atomically moves to the final path.
        Skips if the target file already exists.
        """
        # Validate command format
        if not re.match(r"^/book_[A-Za-z0-9_]+$", command):
            raise TgbookError(
                ErrorCode.INVALID_INPUT_OR_CONFIG,
                f"Invalid download command: {command}",
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        # Send the command
        sent_id = await self._gateway.send_text(command)

        # Wait for a document message from the bot
        doc_msg = await self._wait_for_message(
            after_id=sent_id,
            predicate=lambda m: m.document is not None,
        )

        if doc_msg.document is None:
            raise TgbookError(
                ErrorCode.DOWNLOAD_FAILED,
                "Bot did not return a downloadable file.",
            )

        filename = doc_msg.document[0]
        final_path = output_dir / filename

        # Skip if already exists
        if final_path.exists():
            return DownloadedFile(
                path=final_path,
                filename=filename,
                skipped=True,
            )

        # Download to temp file, then atomic rename
        tmp_path = output_dir / f".{filename}.part"
        try:
            await self._gateway.download_document(doc_msg, tmp_path)
            tmp_path.replace(final_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

        file_size = final_path.stat().st_size

        return DownloadedFile(
            path=final_path,
            filename=filename,
            size=file_size,
            skipped=False,
        )

    async def _wait_for_message(
        self,
        after_id: int,
        predicate,
    ) -> IncomingMessage:
        """Poll for a message matching the predicate within the deadline."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._deadline
        while loop.time() < deadline:
            messages = await self._gateway.messages_after(after_id)
            for message in messages:
                if (message.chat_id == self._gateway.bot_chat_id
                        and message.sender_id == self._gateway.bot_user_id
                        and predicate(message)):
                    return message
            await asyncio.sleep(0.5)
        raise TgbookError(
            ErrorCode.RESPONSE_TIMEOUT,
            "The book bot did not respond within 60 seconds.",
        )

    async def _wait_for_edit(
        self,
        message_id: int,
        predicate,
        previous_text: str | None = None,
    ) -> IncomingMessage:
        """Poll for an edit to a specific message within the deadline."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._deadline
        while loop.time() < deadline:
            msg = await self._gateway.get_message(message_id)
            if msg is not None and msg.text != previous_text and predicate(msg):
                return msg
            await asyncio.sleep(0.5)
        raise TgbookError(
            ErrorCode.RESPONSE_TIMEOUT,
            "The book bot did not edit the message within 60 seconds.",
        )
