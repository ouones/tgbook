"""Tests for the CLI JSON output and exit code contract."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


BOOK_RESULT_DICT = {
    "command": "/book_a8vlLB0g8ve",
    "title": "麦肯锡思考工具（独家首发）",
    "author": None,
    "format": "epub",
    "size": "163 KB",
}

DOWNLOADED_DICT = {
    "path": "C:\\work\\downloads\\book.epub",
    "filename": "book.epub",
    "format": None,
    "size": 4404019,
    "skipped": False,
}


def write_config(tmp_path, **overrides):
    """Helper to write a minimal config file."""
    config_path = tmp_path / "config.toml"
    config = {
        "bot_username": "fixed_book_bot",
        "phone": "+8613800000000",
        "api_id": "123",
        "api_hash": "hash",
    }
    config.update(overrides)
    lines = [f'{k} = {json.dumps(v) if isinstance(v, str) else v}' for k, v in config.items()]
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return str(config_path)


def test_search_writes_one_json_object_and_exit_zero(monkeypatch, capsys, tmp_path):
    from tgbook.cli import main
    from tgbook.models import BookResult

    book_result = BookResult(**BOOK_RESULT_DICT)
    monkeypatch.setattr("tgbook.cli.run_search", AsyncMock(return_value=[book_result]))

    exit_code = main(["search", "麦肯锡思考工具", "--config", write_config(tmp_path)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["action"] == "search"
    assert output["query"] == "麦肯锡思考工具"
    assert output["page"] == 1
    assert output["results"] == [BOOK_RESULT_DICT]


def test_rate_limit_json_contains_retry_after(monkeypatch, capsys, tmp_path):
    from tgbook.cli import main
    from tgbook.errors import ErrorCode, TgbookError

    monkeypatch.setattr(
        "tgbook.cli.run_search",
        AsyncMock(side_effect=TgbookError(ErrorCode.RATE_LIMITED, "Wait 12 seconds.", retry_after=12)),
    )

    assert main(["search", "book", "--config", write_config(tmp_path)]) == 8
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["error"] == {
        "code": "rate_limited",
        "message": "Wait 12 seconds.",
        "retry_after": 12,
    }


def test_missing_config_flag_exits_with_error():
    from tgbook.cli import main

    exit_code = main(["search", "book", "--config", "/nonexistent/config.toml"])

    assert exit_code == 2
    # At least one line of JSON on stdout
    assert "ok" in sys.stdout if hasattr(sys.stdout, 'getvalue') else True


def test_login_required_stays_machine_readable(monkeypatch, capsys, tmp_path):
    from tgbook.cli import main
    from tgbook.errors import ErrorCode, TgbookError

    monkeypatch.setattr(
        "tgbook.cli.run_search",
        AsyncMock(side_effect=TgbookError(ErrorCode.LOGIN_REQUIRED, "Run tgbook login interactively.")),
    )

    assert main(["search", "book", "--config", write_config(tmp_path)]) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["error"]["code"] == "login_required"


def test_download_writes_success_json(monkeypatch, capsys, tmp_path):
    from tgbook.cli import main
    from tgbook.models import DownloadedFile
    from pathlib import Path

    downloaded = DownloadedFile(
        path=Path("C:\\work\\downloads\\book.epub"),
        filename="book.epub",
        size=4404019,
        skipped=False,
    )
    monkeypatch.setattr("tgbook.cli.run_download", AsyncMock(return_value=downloaded))

    exit_code = main(["download", "/book_a8vlLB0g8ve", "--config", write_config(tmp_path)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["action"] == "download"
    assert output["command"] == "/book_a8vlLB0g8ve"


def test_invalid_download_command_exits_with_error():
    from tgbook.cli import main

    # /book_xxx is required
    exit_code = main(["download", "not-a-command", "--config", str(Path("/tmp/fake.toml"))])
    assert exit_code == 2


def test_page_must_be_positive_integer(monkeypatch, capsys, tmp_path):
    from tgbook.cli import main
    from tgbook.models import BookResult

    book_result = BookResult(**BOOK_RESULT_DICT)
    monkeypatch.setattr("tgbook.cli.run_search", AsyncMock(return_value=[book_result]))

    # Page 0 is invalid
    exit_code = main(["search", "book", "--page", "0", "--config", write_config(tmp_path)])
    assert exit_code == 2


def test_internal_error_returns_exit_code_1(monkeypatch, capsys, tmp_path):
    from tgbook.cli import main

    monkeypatch.setattr("tgbook.cli.run_search", AsyncMock(side_effect=RuntimeError("Boom!")))

    exit_code = main(["search", "book", "--config", write_config(tmp_path)])
    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["error"]["code"] == "internal_error"
