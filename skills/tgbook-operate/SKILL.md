---
name: tgbook-operate
description: Operate the tgbook CLI to search and download books from a Telegram book bot. Handles login, search, download, and structured error responses.
---

# tgbook-operate

Use the `tgbook` CLI to search a Telegram book bot and download books by their `/book_xxx` command. Never bypass the CLI through Kurigram or direct Telegram calls.

## Prerequisites

A human must run `tgbook login` once before automated use. This is an interactive command that prompts for a Telegram verification code and optional two-step password.

## Operation Sequence

### 1. Search for Books

```
tgbook search "<book title>" [--page N] [--config PATH]
```

Parse the single JSON object on standard output. The `results` array contains objects with a `command` field (e.g., `/book_a8vlLB0g8ve`). Preserve this exact `command` value — do not infer a selection from list position.

**Success output:**
```json
{
  "ok": true,
  "action": "search",
  "query": "book title",
  "page": 1,
  "results": [
    {
      "command": "/book_123",
      "title": "Example title",
      "author": null,
      "format": "EPUB",
      "size": "4.2 MB"
    }
  ]
}
```

### 2. Download a Book

```
tgbook download /book_xxx [--output DIR] [--config PATH]
```

Supply only the exact `command` value from a search result. The default output directory is `downloads/` under the current working directory.

**Success output:**
```json
{
  "ok": true,
  "action": "download",
  "command": "/book_123",
  "path": "C:\\work\\downloads\\book.epub",
  "filename": "book.epub",
  "format": "EPUB",
  "size": 4404019,
  "skipped": false
}
```

## Error Handling

Every invocation returns exactly one JSON object and a stable exit code. Parse both to determine the result.

### login_required (exit code 3)

The session is missing or invalid. Stop automated work and request that a human run `tgbook login` interactively. Do not attempt to authorize programmatically.

### rate_limited (exit code 8)

The `error` object contains a `retry_after` field with the wait duration in seconds:

```json
{
  "ok": false,
  "error": {
    "code": "rate_limited",
    "message": "Rate limited: wait 12 seconds.",
    "retry_after": 12
  }
}
```

Honor `retry_after` before retrying. Do not resend the original query before waiting.

### account_busy (exit code 4)

Another `tgbook` process is using the account. Retry after a short wait. Do not resend an unconfirmed request.

### response_timeout (exit code 6)

The bot did not respond within 60 seconds. Retry is safe — the original request may or may not have been processed.

### telegram_error (exit code 9)

A Telegram or network error occurred. Retry with backoff.

### no_results (exit code 5)

The search completed but returned no selectable `/book_xxx` commands.

### protocol_error (exit code 7)

The bot's response format did not match expectations. Do not retry automatically — report to a human.

### download_failed (exit code 10)

The media could not be saved to the requested output path. Check disk space and permissions.

### invalid_input_or_config (exit code 2)

The command input or configuration is invalid. Check the arguments and configuration file.

### internal_error (exit code 1)

An unexpected internal error occurred. Report to a human.

## Security

- Exclude phone numbers, `api_hash`, session file contents, and configuration secrets from all outputs and logs.
- The session file at `<data-root>/session/<phone>.session` contains sensitive credentials — never read, copy, or transmit it.
- Environment variables `TGBOOK_API_ID` and `TGBOOK_API_HASH` are sensitive — never log them.
