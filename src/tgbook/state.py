"""OS-level account lock and atomic command-to-path download index."""

from __future__ import annotations

import json
from pathlib import Path

from filelock import FileLock, Timeout

from tgbook.errors import ErrorCode, TgbookError


class AccountLock:
    """Non-blocking OS-level exclusive lock for one Telegram account.

    Only one tgbook process may hold this lock per phone number at a time.
    The OS releases the lock automatically if the process exits unexpectedly.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = FileLock(str(path))

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire(timeout=0)
        except Timeout:
            raise TgbookError(
                ErrorCode.ACCOUNT_BUSY,
                "Another tgbook process is using this account.",
            )

    def release(self) -> None:
        self._lock.release()


class DownloadIndex:
    """Atomic JSON file mapping /book_xxx commands to absolute file paths.

    Used for download idempotency: if the same command was previously
    downloaded and the file still exists, we skip contacting the bot.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise TgbookError(
                ErrorCode.INVALID_INPUT_OR_CONFIG,
                f"Corrupted download index at {self.path}",
            )

    def _write(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(values, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def lookup(self, command: str) -> Path | None:
        raw_path = self._read().get(command)
        if raw_path is None:
            return None
        candidate = Path(raw_path)
        if candidate.is_file():
            return candidate
        self.discard(command)
        return None

    def record(self, command: str, path: Path) -> None:
        values = self._read()
        values[command] = str(path.resolve())
        self._write(values)

    def discard(self, command: str) -> None:
        values = self._read()
        if command in values:
            del values[command]
            self._write(values)
