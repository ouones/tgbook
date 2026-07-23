# tgbook Design

## Context

`tgbook` is an independent command-line tool for a single, preselected Telegram book bot. It uses a Telegram user account, not a Telegram bot token, to search the bot by book title, select a returned `/book_xxx` command, and download the media file returned in the same private chat.

The tool reuses the relevant design proven in EmbyKeeper: Kurigram through the `pyrogram` API, `tgcrypto`, and persistent file-based SQLite sessions. It does not reuse or depend on EmbyKeeper's multi-account pools, check-in framework, OCR, caches, or site configuration.

## Goals

- Provide non-interactive, Agent-friendly `search` and `download` commands.
- Keep Telegram credentials and session material outside the Git repository and outside command JSON output.
- Restrict all bot interaction to one configured bot's private chat.
- Return one machine-readable JSON object and a stable exit code for every invocation.
- Make concurrent use of the same Telegram account fail immediately rather than interleave chat messages.

## Non-Goals

- Supporting multiple book bots, groups, channels, forwarded messages, or generic Telegram automation.
- An interactive terminal search UI.
- Batch downloads, download history, resume support, automatic retries, or queued concurrent work.
- Automatic bot onboarding such as sending `/start`.

## Dependencies and Boundaries

The runtime depends directly on `kurigram` and `tgcrypto`. It implements a small client factory and a bot-specific protocol adapter rather than importing EmbyKeeper source code.

The session behavior follows EmbyKeeper's file-session design:

- A local SQLite `.session` file is the sole persistent login state.
- The configuration file never contains a session string.
- On first login, Kurigram's interactive authorization obtains the verification code and, when enabled, the two-step-verification password, then writes the session file.
- Later commands open that file without interactive prompts.
- A missing or invalid session causes a structured error that directs the caller to run `tgbook login`; a non-login command never attempts to authorize interactively.

## Configuration and Local State

The default configuration is `%LOCALAPPDATA%\tgbook\config.toml`. Its data root is `%LOCALAPPDATA%\tgbook\`.

`--config PATH` takes precedence over `TGBOOK_CONFIG`. When either is supplied, the configuration is read from that path and the data root is the configuration file's parent directory plus `data/`. This lets an Agent use an explicit, portable configuration root.

After applying environment-variable overrides, the resolved configuration must contain these values. A TOML configuration normally contains them directly:

```toml
bot_username = "example_book_bot"
phone = "+8613800000000"
api_id = 123456
api_hash = "telegram-application-hash"
```

Environment variables `TGBOOK_BOT_USERNAME`, `TGBOOK_PHONE`, `TGBOOK_API_ID`, and `TGBOOK_API_HASH` override their respective configuration values. The selected bot username is resolved once at startup and must identify a Telegram bot. The tool uses that resolved bot ID for all response filtering.

Local state paths are:

```text
<data-root>/session/<phone>.session
<data-root>/locks/<phone>.lock
<data-root>/download-index.json
```

The session file is sensitive credential material. It is never serialized to TOML, printed, copied from EmbyKeeper, or committed. On Windows, the tool creates the data directories before use and relies on the current user's filesystem permissions.

## Architecture

### CLI Layer

The CLI parses commands, resolves configuration, obtains the account lock, invokes one operation, and emits the final JSON object. Informational and diagnostic logging goes only to standard error.

### Telegram Client Factory

The factory creates a Kurigram client with a named on-disk session and the chosen data root as its work directory. `login` permits interactive authorization. `search` and `download` first require that the session file exists and then start the client with interactive authorization disabled.

### Book Bot Protocol Adapter

The adapter contains the fixed bot protocol. It has no support for arbitrary bot schemas or user-configurable selectors.

For every operation, it resolves the configured bot into a private chat and records the outgoing request message ID. It only accepts later messages or edits from that bot ID in that private chat; historical messages and messages from any other chat are ignored.

`search` sends the title text, waits for the bot's result message, extracts `/book_xxx` commands, and derives metadata from the corresponding result text. Metadata that the bot does not expose is `null`. For `--page N`, it sends a new search request, parses page one, and clicks that result message's next-page inline button once per page transition until page `N` is parsed. A button click may edit the same message, so both new-message and message-edit updates are observed.

`download` sends the supplied `/book_xxx` command and waits for a downloadable media message from the bot. The adapter accepts document media such as EPUB and PDF and obtains the server-provided filename, MIME type, and size where available. A text response without downloadable media is not a successful download.

### Account Lock

Before connecting, a command opens `<data-root>/locks/<phone>.lock` and obtains an operating-system-level exclusive lock. Lock acquisition is non-blocking, and the operating system releases the lock if the owning process exits unexpectedly. If another `tgbook` process owns the lock, the new command returns `account_busy` and sends no Telegram message. The owner releases the lock after success, failure, or timeout.

## Command Contract

All commands write exactly one JSON object to standard output. Normal logs and progress never use standard output. Success exits with code `0`.

```text
tgbook login [--config PATH]
tgbook search "book title" [--page N] [--config PATH]
tgbook download /book_xxx [--output DIR] [--config PATH]
```

`login` is the only interactive command. Its success response contains only a masked account identifier and `session_created: true`.

`search` defaults to page `1`. It returns only the requested page:

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

`download` accepts only the original `command` from a search result, never a result index. Its default output directory is `downloads/` under the invocation's current working directory. `--output DIR` changes the directory only for the current invocation.

After a successful download, `download-index.json` records only the mapping from `/book_xxx` to the final absolute path. This is an implementation detail for idempotency, not a user-facing download history. When the same command is requested again and its indexed file still exists, `tgbook` returns it with `skipped: true` without contacting the bot. If the indexed file no longer exists, the stale mapping is removed and the normal download flow resumes. For a command with no usable mapping, the bot must be contacted to learn its filename; if that filename already exists in the target output directory, the tool returns `skipped: true` and never overwrites it. Downloads write to a temporary file and atomically move it to the final path only after success, so a failed download leaves no partial final file.

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

## Timeouts, Errors, and Exit Codes

Each bot operation has a single 60-second response deadline. The deadline covers waiting for the initial result, page edits, and the media response. The tool never automatically resends a title or `/book_xxx` command. The calling Agent owns retry and backoff policy.

On failure, the CLI emits:

```json
{
  "ok": false,
  "error": {
    "code": "response_timeout",
    "message": "The book bot did not respond within 60 seconds.",
    "retry_after": null
  }
}
```

The error `code` and process exit code are stable:

| Exit code | Error code | Meaning |
| --- | --- | --- |
| 1 | `internal_error` | Unexpected local failure. |
| 2 | `invalid_input_or_config` | Invalid command input or missing/invalid configuration. |
| 3 | `login_required` | No usable session exists or the session is invalid. |
| 4 | `account_busy` | Another process owns the account lock. |
| 5 | `no_results` | Search completed but returned no selectable `/book_xxx` command. |
| 6 | `response_timeout` | The bot did not provide the required response within 60 seconds. |
| 7 | `protocol_error` | The bot response or pagination markup did not match the fixed protocol. |
| 8 | `rate_limited` | Telegram returned a FloodWait; `retry_after` contains its wait duration. |
| 9 | `telegram_error` | Other Telegram or transport failure. |
| 10 | `download_failed` | Media could not be saved to the requested output path. |

All errors leave existing output files untouched. Errors other than `rate_limited` return `retry_after: null`.

## Agent Operation Skill

After the CLI implementation is complete, the repository contains the canonical cross-agent skill at `skills/tgbook-operate/SKILL.md`. Hermes reads this file directly from the repository. Codex, Claude Code, and other Agent runtimes may load the same file through their own orchestration; the project does not install, copy, or link it into any global Agent directory.

The skill uses portable `name` and `description` frontmatter and contains no runtime-specific metadata. It instructs an Agent to:

- Use only `tgbook login`, `tgbook search`, and `tgbook download`; never bypass the CLI through Kurigram or direct Telegram calls.
- Treat `login` as a human-only interactive operation. On `login_required`, stop automated work and request that a human run it.
- Preserve the `command` returned by `search` exactly and supply only that `/book_xxx` value to `download`; never infer a selection from a list position.
- Treat the single JSON object on standard output plus the process exit code as the result; never parse standard-error logs as a result.
- Honor `rate_limited.retry_after`. Leave retries for `account_busy`, timeout, and Telegram/network failures to the calling scheduler, without resending an unconfirmed request.
- Exclude phone numbers, `api_hash`, session contents, and configuration secrets from outputs and Agent logs.

## Verification Strategy

- Unit tests use saved text and inline-keyboard fixtures to test `/book_xxx` extraction, metadata parsing, page selection, and malformed bot responses.
- Adapter flow tests use a simulated Kurigram client to cover successful search, edited pagination, media download, missing session, lock contention, timeout, FloodWait, command-index skips, stale-index removal, and file-exists behavior.
- CLI tests assert one JSON object on standard output and the exact exit code for every success and error category.
- Skill validation checks the `tgbook-operate` frontmatter and exercises its documented success and error-handling procedure against CLI fixtures.
- A manual integration checklist verifies a real `login`, first-page search, paged search, and one media download. Test fixtures never contain Telegram credentials, a session file, or real downloaded books.

## Acceptance Criteria

1. A user can run `tgbook login` once and later run `tgbook search` and `tgbook download` without a terminal prompt.
2. All bot interaction uses only the configured bot's private chat.
3. Search returns only the selected page with stable `/book_xxx` commands and nullable metadata fields.
4. Download accepts a returned command, writes the file to the required directory, skips a previously indexed command without contacting Telegram, and never overwrites a same-named existing file.
5. Every invocation produces exactly one JSON object and the documented exit code.
6. A concurrent invocation for the same account returns `account_busy` without messaging the bot.
7. The automated tests cover the parser, protocol flow, JSON contract, and all documented error mappings.
8. `skills/tgbook-operate/SKILL.md` teaches Hermes, Codex, and Claude Code-compatible Agents to operate only through the CLI and to handle structured failures safely.
