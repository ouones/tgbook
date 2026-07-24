"""Typed operational errors and stable exit-code mapping."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    INTERNAL_ERROR = "internal_error"
    INVALID_INPUT_OR_CONFIG = "invalid_input_or_config"
    LOGIN_REQUIRED = "login_required"
    ACCOUNT_BUSY = "account_busy"
    NO_RESULTS = "no_results"
    RESPONSE_TIMEOUT = "response_timeout"
    PROTOCOL_ERROR = "protocol_error"
    RATE_LIMITED = "rate_limited"
    TELEGRAM_ERROR = "telegram_error"
    DOWNLOAD_FAILED = "download_failed"


EXIT_CODES: dict[ErrorCode, int] = {
    ErrorCode.INTERNAL_ERROR: 1,
    ErrorCode.INVALID_INPUT_OR_CONFIG: 2,
    ErrorCode.LOGIN_REQUIRED: 3,
    ErrorCode.ACCOUNT_BUSY: 4,
    ErrorCode.NO_RESULTS: 5,
    ErrorCode.RESPONSE_TIMEOUT: 6,
    ErrorCode.PROTOCOL_ERROR: 7,
    ErrorCode.RATE_LIMITED: 8,
    ErrorCode.TELEGRAM_ERROR: 9,
    ErrorCode.DOWNLOAD_FAILED: 10,
}


class TgbookError(Exception):
    """Application error with stable machine-readable code."""

    def __init__(self, code: ErrorCode, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


def exit_code(error: TgbookError) -> int:
    """Return the process exit code for a TgbookError."""
    return EXIT_CODES.get(error.code, 1)
