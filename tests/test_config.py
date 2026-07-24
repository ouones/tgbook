"""Tests for tgbook.config.load_config."""

import json
import os
import sys
from pathlib import Path

import pytest

# Add src to path for testing before package is installed
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def write_config(tmp_path, **overrides):
    """Helper to write a minimal config file."""
    config_path = tmp_path / "config.toml"
    config = {
        "bot_username": "fixed_book_bot",
        "phone": "+8613800000000",
        "api_id": 123,
        "api_hash": "hash",
    }
    config.update(overrides)
    lines = [f'{k} = {json.dumps(v) if isinstance(v, str) else v}' for k, v in config.items()]
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def test_explicit_config_uses_sibling_data_directory(tmp_path, monkeypatch):
    from tgbook.config import load_config

    config_path = tmp_path / "agent" / "config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        'bot_username = "fixed_book_bot"\nphone = "+8613800000000"\n'
        'api_id = 123\napi_hash = "hash"\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.data_root == config_path.parent / "data"
    assert config.session_path == config.data_root / "session" / "+8613800000000.session"


def test_environment_overrides_toml_values(tmp_path, monkeypatch):
    from tgbook.config import load_config

    config_path = write_config(tmp_path)
    monkeypatch.setenv("TGBOOK_BOT_USERNAME", "other_book_bot")
    monkeypatch.setenv("TGBOOK_API_ID", "456")

    config = load_config(config_path)

    assert config.bot_username == "other_book_bot"
    assert config.api_id == 456


def test_missing_config_field_raises(tmp_path):
    from tgbook.config import load_config
    from tgbook.errors import TgbookError, ErrorCode

    config_path = tmp_path / "config.toml"
    config_path.write_text('bot_username = "fixed_book_bot"\n', encoding="utf-8")

    with pytest.raises(TgbookError) as exc:
        load_config(config_path)
    assert exc.value.code == ErrorCode.INVALID_INPUT_OR_CONFIG


def test_default_data_root_uses_localappdata(tmp_path, monkeypatch):
    from tgbook.config import load_config

    localappdata = tmp_path / "AppData" / "Local"
    localappdata.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

    config_path = write_config(tmp_path)

    # When no explicit path given and no TGBOOK_CONFIG, default root is LOCALAPPDATA\tgbook
    config = load_config(config_path)
    # With explicit config, data_root is sibling data/ directory
    assert config.data_root == config_path.parent / "data"
