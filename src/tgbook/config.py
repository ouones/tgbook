"""TOML/environment configuration resolution and state-path calculation."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from tgbook.errors import ErrorCode, TgbookError
from tgbook.models import AppConfig


def _default_data_root() -> Path:
    if os.name == "nt":
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            return Path(localappdata) / "tgbook"
        return Path.home() / "AppData" / "Local" / "tgbook"
    # Linux, macOS, etc.
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "tgbook"
    return Path.home() / ".local" / "share" / "tgbook"


def load_config(explicit_path: Path | None = None) -> AppConfig:
    """Load and resolve configuration from TOML and environment variables.

    Precedence (highest first):
    1. Environment variables (TGBOOK_BOT_USERNAME, TGBOOK_PHONE, TGBOOK_API_ID, TGBOOK_API_HASH)
    2. TOML configuration file
    """
    # Determine config path
    if explicit_path is not None:
        config_path = explicit_path
    else:
        env_config = os.environ.get("TGBOOK_CONFIG")
        if env_config:
            config_path = Path(env_config)
        else:
            config_path = _default_data_root() / "config.toml"

    # Read TOML
    raw: dict = {}
    if config_path.is_file():
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    # Apply environment overrides
    bot_username = os.environ.get("TGBOOK_BOT_USERNAME", raw.get("bot_username"))
    phone = os.environ.get("TGBOOK_PHONE", raw.get("phone"))
    api_id_str = os.environ.get("TGBOOK_API_ID", str(raw.get("api_id", "")))
    api_hash = os.environ.get("TGBOOK_API_HASH", raw.get("api_hash"))
    proxy = os.environ.get("TGBOOK_PROXY", raw.get("proxy"))

    # Validate required fields
    missing = []
    if not bot_username:
        missing.append("bot_username")
    if not phone:
        missing.append("phone")
    if not api_id_str or api_id_str == "None":
        missing.append("api_id")
    if not api_hash:
        missing.append("api_hash")

    if missing:
        raise TgbookError(
            ErrorCode.INVALID_INPUT_OR_CONFIG,
            f"Missing required configuration fields: {', '.join(missing)}",
        )

    # Convert api_id to int
    try:
        api_id = int(api_id_str)
    except (ValueError, TypeError):
        raise TgbookError(
            ErrorCode.INVALID_INPUT_OR_CONFIG,
            f"api_id must be an integer, got: {api_id_str}",
        )

    # Data root is the config file's sibling data/ directory
    data_root = config_path.parent / "data"

    return AppConfig(
        bot_username=str(bot_username),
        phone=str(phone),
        api_id=api_id,
        api_hash=str(api_hash),
        proxy=str(proxy) if proxy else None,
        config_path=config_path,
        data_root=data_root,
    )
