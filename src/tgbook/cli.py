"""argparse commands and JSON-only standard output."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Sequence

from tgbook.book_bot import BookBotService
from tgbook.config import load_config
from tgbook.errors import ErrorCode, TgbookError, exit_code as error_exit_code
from tgbook.models import BookResult, DownloadedFile
from tgbook.state import AccountLock, DownloadIndex
from tgbook.telegram import KurigramGateway


def emit(value: dict) -> None:
    """Write one JSON object to standard output."""
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), file=sys.stdout)


def emit_error(error: TgbookError) -> int:
    """Emit a machine-readable error and return the exit code."""
    emit({
        "ok": False,
        "error": {
            "code": error.code.value,
            "message": error.message,
            "retry_after": error.retry_after,
        },
    })
    return error_exit_code(error)


async def run_login(config) -> dict:
    """Run interactive login. Returns the success result dict."""
    gw = KurigramGateway(config, interactive=True)
    await gw.start()
    try:
        pass  # Login is triggered by gateway start
    finally:
        await gw.stop()
    return {
        "ok": True,
        "action": "login",
        "phone": config.phone[:4] + "****" + config.phone[-2:],
        "session_created": True,
    }


async def run_search(config, query: str, page: int) -> list[BookResult]:
    """Run a search and return results."""
    gw = KurigramGateway(config, interactive=False)
    await gw.start()
    try:
        service = BookBotService(gw)
        return await service.search(query, page)
    finally:
        await gw.stop()


async def run_download(config, command: str, output: Path) -> DownloadedFile:
    """Run a download and return the result."""
    # Check download index first
    index = DownloadIndex(config.download_index_path)
    cached = index.lookup(command)
    if cached is not None:
        return DownloadedFile(
            path=cached,
            filename=cached.name,
            skipped=True,
        )

    gw = KurigramGateway(config, interactive=False)
    await gw.start()
    try:
        service = BookBotService(gw)
        result = await service.download(command, output)
    finally:
        await gw.stop()

    # Record in index for future idempotency
    if not result.skipped:
        index.record(command, result.path)

    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the tgbook CLI. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="tgbook",
        description="Agent-friendly Telegram book bot CLI",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # login
    login_parser = subparsers.add_parser("login", help="Interactive session login")
    login_parser.add_argument("--config", type=Path, default=None, help="Path to config.toml")

    # search
    search_parser = subparsers.add_parser("search", help="Search for books")
    search_parser.add_argument("query", type=str, help="Book title to search for")
    search_parser.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    search_parser.add_argument("--config", type=Path, default=None, help="Path to config.toml")

    # download
    download_parser = subparsers.add_parser("download", help="Download a book by command")
    download_parser.add_argument("book_command", type=str, help="The /book_xxx command from search results")
    download_parser.add_argument("--output", type=Path, default=None, help="Output directory")
    download_parser.add_argument("--config", type=Path, default=None, help="Path to config.toml")

    args = parser.parse_args(argv)

    # Early validation before config load
    if args.command == "search" and args.page < 1:
        emit({
            "ok": False,
            "error": {
                "code": ErrorCode.INVALID_INPUT_OR_CONFIG.value,
                "message": "Page must be a positive integer.",
                "retry_after": None,
            },
        })
        return error_exit_code(
            TgbookError(ErrorCode.INVALID_INPUT_OR_CONFIG, "Page must be a positive integer.")
        )

    if args.command == "download":
        if not re.match(r"^/book_[A-Za-z0-9_]+$", args.book_command):
            emit({
                "ok": False,
                "error": {
                    "code": ErrorCode.INVALID_INPUT_OR_CONFIG.value,
                    "message": f"Invalid download command: '{args.book_command}'. Must be a /book_xxx command from search results.",
                    "retry_after": None,
                },
            })
            return error_exit_code(
                TgbookError(
                    ErrorCode.INVALID_INPUT_OR_CONFIG,
                    f"Invalid download command: '{args.book_command}'.",
                )
            )

    # Load config
    try:
        config = load_config(args.config)
    except TgbookError as e:
        return emit_error(e)

    # Acquire account lock (not needed for login)
    lock = None
    if args.command != "login":
        lock = AccountLock(config.lock_path)
        try:
            lock.acquire()
        except TgbookError as e:
            return emit_error(e)

    exit_code = 1
    try:
        async def _run_command() -> int:
            if args.command == "login":
                result = await run_login(config)
                emit(result)
                return 0
            elif args.command == "search":
                results = await run_search(config, args.query, args.page)
                emit({
                    "ok": True,
                    "action": "search",
                    "query": args.query,
                    "page": args.page,
                    "results": [r.to_dict() for r in results],
                })
                return 0
            elif args.command == "download":
                output_dir = args.output or (Path.cwd() / "downloads")
                result = await run_download(config, args.book_command, output_dir)
                emit({
                    "ok": True,
                    "action": "download",
                    "command": args.book_command,
                    "path": str(result.path),
                    "filename": result.filename,
                    "format": result.format,
                    "size": result.size,
                    "skipped": result.skipped,
                })
                return 0
            return 1

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            exit_code = loop.run_until_complete(_run_command())
        finally:
            loop.close()

    except TgbookError as e:
        exit_code = emit_error(e)
    except Exception as e:
        exit_code = emit_error(
            TgbookError(ErrorCode.INTERNAL_ERROR, f"internal error: {e}")
        )
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass

    return exit_code
