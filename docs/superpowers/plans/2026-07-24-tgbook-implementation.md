# tgbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tgbook`, an Agent-friendly CLI that privately searches one configured Telegram book bot and downloads a selected result through Kurigram.

**Architecture:** Keep the CLI, persistent local state, Kurigram transport, and the fixed book-bot protocol in separate modules. The CLI owns configuration, locking, JSON output, and exit codes; the protocol layer owns the text/keyboard format shown in the supplied Telegram capture. A repository-local `tgbook-operate` skill teaches Agents to use the CLI rather than accessing Telegram directly.

**Tech Stack:** Python 3.11+, Kurigram 2.2.12, tgcrypto, filelock, standard-library `argparse`, `tomllib`, and `json`, pytest.

## Global Constraints

- Create all implementation files under `E:\tgbook`; do not import or copy EmbyKeeper production modules.
- Pin `kurigram==2.2.12` and use `tgcrypto` for MTProto acceleration.
- Require Python `>=3.11` so TOML parsing uses `tomllib` without another dependency.
- Store Telegram session state only in `<data-root>/session/<phone>.session`; never store or print a session string.
- Default configuration root is `%LOCALAPPDATA%\tgbook`; explicit `--config` and `TGBOOK_CONFIG` use the configuration file's parent `data/` directory as the data root.
- Interact only with the configured Telegram bot in a private chat, and only after holding a non-blocking OS-level account lock.
- Send exactly one JSON object to standard output per command. Send logs only to standard error.
- Use a 60-second operation deadline and never automatically resend a search query or `/book_xxx` command.
- Use `/book_xxx` as the only download selection identifier. Do not select by result position.
- Do not commit credentials, `.session` files, downloaded books, or `download-index.json`.

## Reference Inputs

The implementation is independent of EmbyKeeper. Read only these narrow references when the Kurigram behavior needs confirmation:

- `E:\embykeeper\embykeeper\telegram\pyrogram.py:219` for durable SQLite storage behavior, `:393` for its `pyrogram.Client` wrapper, and `:524`, `:569`, `:582` for reply/edit waiting patterns.
- `E:\embykeeper\embykeeper\telegram\checkiner\_templ_a.py:93` for `message.click(...)` on inline keyboard buttons.

The supplied Telegram capture defines the initial fixed protocol fixture:

```text
Good news! We found 9 📚 on your request:

📚 <title>
<optional author>
Year: <year>
🌐 <language>
/book_<opaque-id> (<epub|pdf>, <human size>)

inline button: (2) next »
```

After a `/book_<opaque-id>` request, the bot may send a metadata text message followed by a Telegram document. Treat the document as the successful media response.

## File Structure

```text
pyproject.toml                     Packaging, dependencies, pytest settings, and `tgbook` script.
.gitignore                         Excludes local config, sessions, locks, indexes, and downloads.
src/tgbook/__init__.py             Package version.
src/tgbook/__main__.py             Supports `python -m tgbook`.
src/tgbook/models.py               Immutable config, result, message, and output dataclasses.
src/tgbook/errors.py               Typed operational errors and stable exit-code mapping.
src/tgbook/config.py               TOML/environment resolution and state-path calculation.
src/tgbook/state.py                OS lock plus atomic command-to-path index.
src/tgbook/parser.py               Fixed search text and pagination parsing.
src/tgbook/telegram.py             Kurigram client lifecycle and private-chat transport adapter.
src/tgbook/book_bot.py             Search, pagination, media wait, and atomic download workflow.
src/tgbook/cli.py                  argparse commands and JSON-only standard output.
tests/conftest.py                  Fake transport and shared temporary configuration helpers.
tests/fixtures/search-page-1.txt   Redacted page-one message based on the supplied capture.
tests/fixtures/search-page-2.txt   Redacted page-two message using the same format.
tests/test_config.py               Configuration and state-root tests.
tests/test_state.py                Lock and download-index tests.
tests/test_parser.py               Search result and pagination parser tests.
tests/test_book_bot.py             Fixed protocol flow tests with the fake transport.
tests/test_cli.py                  JSON stdout and exit-code contract tests.
skills/tgbook-operate/SKILL.md     Canonical cross-Agent operating skill.
```

### Task 1: Bootstrap the Package, Models, Errors, and Configuration

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/tgbook/__init__.py`, `src/tgbook/__main__.py`, `src/tgbook/models.py`, `src/tgbook/errors.py`, `src/tgbook/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces `load_config(explicit_path: Path | None) -> AppConfig`.
- Produces `AppConfig.bot_username`, `phone`, `api_id`, `api_hash`, `config_path`, and `data_root`.
- Produces `TgbookError(code: ErrorCode, message: str, retry_after: int | None = None)` and `exit_code(error) -> int`.

- [ ] **Step 1: Create the failing configuration tests.**

```python
def test_explicit_config_uses_sibling_data_directory(tmp_path, monkeypatch):
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
    config_path = write_config(tmp_path)
    monkeypatch.setenv("TGBOOK_BOT_USERNAME", "other_book_bot")
    monkeypatch.setenv("TGBOOK_API_ID", "456")

    config = load_config(config_path)

    assert config.bot_username == "other_book_bot"
    assert config.api_id == 456
```

- [ ] **Step 2: Run the tests to verify the package is absent.**

Run: `python -m pytest tests/test_config.py -q`

Expected: FAIL during collection because `tgbook` does not exist.

- [ ] **Step 3: Create the minimal package and packaging configuration.**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "tgbook"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["kurigram==2.2.12", "tgcrypto", "filelock>=3.13"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
tgbook = "tgbook.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# src/tgbook/errors.py
class ErrorCode(StrEnum):
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


EXIT_CODES = {ErrorCode.INTERNAL_ERROR: 1, ErrorCode.INVALID_INPUT_OR_CONFIG: 2,
              ErrorCode.LOGIN_REQUIRED: 3, ErrorCode.ACCOUNT_BUSY: 4,
              ErrorCode.NO_RESULTS: 5, ErrorCode.RESPONSE_TIMEOUT: 6,
              ErrorCode.PROTOCOL_ERROR: 7, ErrorCode.RATE_LIMITED: 8,
              ErrorCode.TELEGRAM_ERROR: 9, ErrorCode.DOWNLOAD_FAILED: 10}
```

Implement `load_config` with `tomllib.loads`, environment overrides, typed `api_id` conversion, and an `invalid_input_or_config` error for a missing field or invalid integer. Compute the default root from `LOCALAPPDATA` and use `Path.home() / "AppData" / "Local"` only when that variable is absent. Add `.gitignore` entries for `.venv/`, `__pycache__/`, `*.session`, `config.toml`, `data/`, `downloads/`, and `download-index.json`.

- [ ] **Step 4: Run the focused tests.**

Run: `python -m pytest tests/test_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the bootstrap.**

```bash
git add pyproject.toml .gitignore src/tgbook tests/test_config.py
git commit -m "feat: bootstrap tgbook configuration"
```

### Task 2: Add Persistent Local State and Non-Blocking Account Locking

**Files:**
- Create: `src/tgbook/state.py`, `tests/test_state.py`
- Modify: `src/tgbook/models.py`, `src/tgbook/config.py`

**Interfaces:**
- Produces `AccountLock(path: Path)` with `acquire() -> None` and `release() -> None`.
- Produces `DownloadIndex(path: Path)` with `lookup(command: str) -> Path | None`, `record(command: str, path: Path) -> None`, and `discard(command: str) -> None`.

- [ ] **Step 1: Write failing tests for the index and lock.**

```python
def test_index_returns_only_an_existing_file(tmp_path):
    index = DownloadIndex(tmp_path / "download-index.json")
    output = tmp_path / "book.epub"
    output.write_bytes(b"book")
    index.record("/book_123", output)

    assert index.lookup("/book_123") == output.resolve()
    output.unlink()
    assert index.lookup("/book_123") is None
    assert "/book_123" not in json.loads(index.path.read_text(encoding="utf-8"))


def test_second_process_cannot_acquire_account_lock(tmp_path):
    lock = AccountLock(tmp_path / "phone.lock")
    lock.acquire()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", LOCK_PROBE, str(lock.path)],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        lock.release()

    assert completed.returncode == 4
```

- [ ] **Step 2: Run the focused tests and verify failure.**

Run: `python -m pytest tests/test_state.py -q`

Expected: FAIL during collection because `tgbook.state` does not exist.

- [ ] **Step 3: Implement atomic index persistence and OS lock ownership.**

```python
class AccountLock:
    def acquire(self) -> None:
        try:
            self._lock.acquire(timeout=0)
        except Timeout:
            raise TgbookError(ErrorCode.ACCOUNT_BUSY, "Another tgbook process is using this account.")


class DownloadIndex:
    def lookup(self, command: str) -> Path | None:
        raw_path = self._read().get(command)
        if raw_path is None:
            return None
        candidate = Path(raw_path)
        if candidate.is_file():
            return candidate
        self.discard(command)
        return None

    def _write(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
```

Use `filelock.FileLock` for the underlying OS-level lock. Make `DownloadIndex.record` store `str(path.resolve())`. Ensure malformed JSON raises `invalid_input_or_config` rather than silently discarding state.

- [ ] **Step 4: Run the state tests.**

Run: `python -m pytest tests/test_state.py -q`

Expected: PASS.

- [ ] **Step 5: Commit state handling.**

```bash
git add src/tgbook/models.py src/tgbook/config.py src/tgbook/state.py tests/test_state.py
git commit -m "feat: add tgbook local state"
```

### Task 3: Parse the Fixed Book-Bot Search and Pagination Protocol

**Files:**
- Create: `src/tgbook/parser.py`, `tests/fixtures/search-page-1.txt`, `tests/fixtures/search-page-2.txt`, `tests/test_parser.py`

**Interfaces:**
- Produces `parse_search_page(text: str) -> list[BookResult]`.
- Produces `find_next_button(rows: Sequence[Sequence[Button]]) -> ButtonRef | None`.
- `BookResult` has `command`, `title`, `author`, `format`, and `size`; absent metadata is `None`.

- [ ] **Step 1: Write parser tests from the supplied bot format.**

```python
def test_parse_search_page_extracts_the_stable_command_and_metadata(load_fixture):
    results = parse_search_page(load_fixture("search-page-1.txt"))

    assert results[0] == BookResult(
        command="/book_a8vlLB0g8ve",
        title="麦肯锡思考工具（独家首发）",
        author=None,
        format="epub",
        size="163 KB",
    )


def test_next_button_requires_the_captured_page_control():
    assert find_next_button([[Button("- 1 -"), Button("(2) next »")]]) == ButtonRef(0, 1)
    assert find_next_button([[Button("- 1 -")]]) is None
```

- [ ] **Step 2: Run parser tests to verify failure.**

Run: `python -m pytest tests/test_parser.py -q`

Expected: FAIL during collection because `tgbook.parser` does not exist.

- [ ] **Step 3: Implement the bounded parser.**

```python
COMMAND_LINE = re.compile(
    r"^(?P<command>/book_[A-Za-z0-9_]+)\s*\((?P<format>[^,()]+),\s*(?P<size>[^()]+)\)$",
    re.MULTILINE,
)
NEXT_BUTTON = re.compile(r"^\(\d+\)\s+next\s+»$", re.IGNORECASE)


def parse_search_page(text: str) -> list[BookResult]:
    results: list[BookResult] = []
    for match in COMMAND_LINE.finditer(text):
        marker = text.rfind("📚", 0, match.start())
        if marker < 0:
            continue
        lines = [line.strip() for line in text[marker + 1:match.start()].splitlines() if line.strip()]
        title = lines[0].removeprefix("📚").strip() if lines else None
        author = next((line for line in lines[1:] if not line.startswith(("Year:", "🌐", "/book_"))), None)
        results.append(BookResult(match["command"], title, author, match["format"].lower(), match["size"]))
    return results
```

For each command match, examine only text after the preceding `📚` marker. Use the first non-empty line as `title`; select the first non-empty line that is not the title, `Year:`, `🌐`, or a command as `author`; extract the `🌐` value only if later metadata is ever exposed. Do not infer an author from a title. `find_next_button` must return the row/column of the only button matching `NEXT_BUTTON`; return `None` for no match or multiple matches, because both are fixed-protocol failures at the caller.

- [ ] **Step 4: Run parser tests.**

Run: `python -m pytest tests/test_parser.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the parser.**

```bash
git add src/tgbook/models.py src/tgbook/parser.py tests/fixtures tests/test_parser.py
git commit -m "feat: parse fixed book bot results"
```

### Task 4: Implement Kurigram Transport and the Bot Operation Service

**Files:**
- Create: `src/tgbook/telegram.py`, `src/tgbook/book_bot.py`, `tests/conftest.py`, `tests/test_book_bot.py`

**Interfaces:**
- Produces `KurigramGateway(config: AppConfig, interactive: bool)` as an async context manager.
- Produces `BookBotService(gateway: BotGateway, deadline_seconds: float = 60.0)` with `search(query: str, page: int) -> list[BookResult]` and `download(command: str, output_dir: Path) -> DownloadedFile`.
- `BotGateway` exposes `send_text`, `messages_after`, `get_message`, `click`, and `download_document` so tests use a fake without Telegram credentials.

- [ ] **Step 1: Write failing service tests with a fake private-chat gateway.**

```python
async def test_search_restarts_at_page_one_then_clicks_next_for_page_two(fake_gateway):
    fake_gateway.queue_search_page(load_fixture("search-page-1.txt"), [["- 1 -", "(2) next »"]])
    fake_gateway.queue_edit(load_fixture("search-page-2.txt"), [["« prev (1)", "- 2 -"]])
    service = BookBotService(fake_gateway)

    results = await service.search("麦肯锡思考工具", page=2)

    assert fake_gateway.sent_text == ["麦肯锡思考工具"]
    assert fake_gateway.clicked == [(fake_gateway.search_message_id, 0, 1)]
    assert results[0].command.startswith("/book_")


async def test_download_waits_for_document_and_moves_the_completed_file(fake_gateway, tmp_path):
    fake_gateway.queue_text("📚 麦肯锡思考工具")
    fake_gateway.queue_document(filename="book.epub", content=b"book")

    downloaded = await BookBotService(fake_gateway).download("/book_aQRMmmPnZRV", tmp_path)

    assert downloaded.path == tmp_path / "book.epub"
    assert downloaded.path.read_bytes() == b"book"
```

- [ ] **Step 2: Run service tests and verify failure.**

Run: `python -m pytest tests/test_book_bot.py -q`

Expected: FAIL during collection because `tgbook.book_bot` does not exist.

- [ ] **Step 3: Implement the real gateway and deadline-controlled service.**

```python
async def wait_for_bot_message(self, after_id: int, predicate: Callable[[IncomingMessage], bool]) -> IncomingMessage:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + self.deadline_seconds
    while loop.time() < deadline:
        for message in await self.gateway.messages_after(after_id):
            if (message.chat_id == self.gateway.bot_chat_id
                    and message.sender_id == self.gateway.bot_user_id
                    and predicate(message)):
                return message
        await asyncio.sleep(0.5)
    raise TgbookError(ErrorCode.RESPONSE_TIMEOUT, "The book bot did not respond within 60 seconds.")
```

Create Kurigram with the session name `config.phone`, `workdir=config.session_path.parent`, `phone_number=config.phone`, `api_id=config.api_id`, `api_hash=config.api_hash`, and `no_updates=True`. Before a non-interactive start, require `config.session_path.is_file()`. Resolve `config.bot_username`, reject a non-bot or non-private chat as `protocol_error`, and keep the resolved bot ID for every gateway response filter. Map `FloodWait.value` to `rate_limited` with `retry_after`; map authorization failures to `login_required`; map remaining `RPCError` and transport failures to `telegram_error`.

For page one, send the query and wait for a bot text message with at least one parsed command. For each further page, locate exactly one `(N) next »` button, call `message.click(row, column)`, and poll `get_message(message.id)` until its text changes and parses. If no matching button exists before reaching the requested page, raise `protocol_error`. For download, validate `^/book_[A-Za-z0-9_]+$`, send it once, ignore text metadata, wait for a document, stream it to a `.part` file beside the final output, then atomically replace the final path. If the final path already exists after the filename is known, return a skipped `DownloadedFile` without opening a download stream.

- [ ] **Step 4: Run the service tests.**

Run: `python -m pytest tests/test_book_bot.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the Telegram operation service.**

```bash
git add src/tgbook/telegram.py src/tgbook/book_bot.py tests/conftest.py tests/test_book_bot.py
git commit -m "feat: operate the fixed Telegram book bot"
```

### Task 5: Add the JSON CLI and End-to-End Contract Tests

**Files:**
- Create: `src/tgbook/cli.py`, `tests/test_cli.py`
- Modify: `src/tgbook/__main__.py`, `src/tgbook/book_bot.py`, `src/tgbook/state.py`

**Interfaces:**
- Produces `main(argv: Sequence[str] | None = None) -> int`.
- Produces `run_login(config: AppConfig) -> LoginResult`, `run_search(config: AppConfig, query: str, page: int) -> list[BookResult]`, and `run_download(config: AppConfig, command: str, output: Path) -> DownloadedFile` for CLI test substitution.
- Supports `tgbook login [--config PATH]`, `tgbook search QUERY [--page N] [--config PATH]`, and `tgbook download COMMAND [--output DIR] [--config PATH]`.

- [ ] **Step 1: Write failing CLI contract tests.**

```python
def test_search_writes_one_json_object_and_exit_zero(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("tgbook.cli.run_search", AsyncMock(return_value=[BOOK_RESULT]))

    exit_code = main(["search", "麦肯锡思考工具", "--config", str(write_config(tmp_path))])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True, "action": "search", "query": "麦肯锡思考工具", "page": 1,
        "results": [BOOK_RESULT.to_dict()],
    }


def test_rate_limit_json_contains_retry_after(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        "tgbook.cli.run_search",
        AsyncMock(side_effect=TgbookError(ErrorCode.RATE_LIMITED, "Wait 12 seconds.", retry_after=12)),
    )

    assert main(["search", "book", "--config", str(write_config(tmp_path))]) == 8
    assert json.loads(capsys.readouterr().out)["error"] == {
        "code": "rate_limited", "message": "Wait 12 seconds.", "retry_after": 12,
    }
```

- [ ] **Step 2: Run CLI tests and verify failure.**

Run: `python -m pytest tests/test_cli.py -q`

Expected: FAIL because `tgbook.cli` does not exist.

- [ ] **Step 3: Implement argparse, command dispatch, lock lifecycle, and output serialization.**

```python
def emit(value: dict[str, object]) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def emit_error(error: TgbookError) -> int:
    emit({"ok": False, "error": {
        "code": error.code.value,
        "message": error.message,
        "retry_after": error.retry_after,
    }})
    return exit_code(error)
```

Use `argparse` with `--page` parsed as a positive integer and command validation for `/book_xxx`. Acquire `AccountLock` before starting Kurigram. For `download`, look up the command in `DownloadIndex` before creating a gateway; when it resolves to an existing file, emit its metadata with `skipped: true` and do not call the protocol service. After a non-skipped successful download, call `DownloadIndex.record(command, downloaded.path)`. Wrap every command in `try/except TgbookError`; wrap unexpected exceptions as `internal_error` without emitting traceback content to standard output. Make `login` use the same client factory with `interactive=True` and return only a masked phone plus `session_created: true`.

- [ ] **Step 4: Run all automated tests.**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit the CLI.**

```bash
git add src/tgbook/cli.py src/tgbook/__main__.py src/tgbook/book_bot.py src/tgbook/state.py tests/test_cli.py
git commit -m "feat: add agent-friendly tgbook cli"
```

### Task 6: Create and Validate the Cross-Agent Operating Skill

**Files:**
- Create: `skills/tgbook-operate/SKILL.md`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces a portable Agent Skill with frontmatter `name: tgbook-operate` and an explicit description for book search, download, and structured error handling.
- Produces no installer, symlink, global Codex metadata, Claude Code metadata, or Hermes-specific manifest.

- [ ] **Step 1: Add a CLI fixture test that the skill can reference.**

```python
def test_login_required_stays_machine_readable(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        "tgbook.cli.run_search",
        AsyncMock(side_effect=TgbookError(ErrorCode.LOGIN_REQUIRED, "Run tgbook login interactively.")),
    )

    assert main(["search", "book", "--config", str(write_config(tmp_path))]) == 3
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "login_required"
```

- [ ] **Step 2: Run the fixture test before writing the skill.**

Run: `python -m pytest tests/test_cli.py::test_login_required_stays_machine_readable -q`

Expected: PASS. Task 5 has already implemented this CLI behavior; the test is a regression guard for the skill's `login_required` procedure.

- [ ] **Step 3: Initialize the skill directory and replace the generated template with the portable operation procedure.**

Run: `python C:\Users\chenlujie\.codex\skills\.system\skill-creator\scripts\init_skill.py tgbook-operate --path E:\tgbook\skills`

Run: `Remove-Item -Recurse -LiteralPath E:\tgbook\skills\tgbook-operate\agents`

The initializer creates Codex-specific `agents/openai.yaml`; remove that generated directory so the repository contains no runtime-specific metadata. Write `skills/tgbook-operate/SKILL.md` with only `name` and `description` frontmatter. Its body must require this sequence: use `tgbook search`; preserve the returned `command`; call `tgbook download` only with that command; parse the single JSON object from standard output; treat `login_required` as a human-login handoff; honor `rate_limited.retry_after`; let the scheduler decide retries for `account_busy`, timeout, and Telegram/network errors; and never log API credentials, phone numbers, or session contents. Explicitly forbid direct Kurigram and Telegram calls.

- [ ] **Step 4: Validate the skill and its referenced CLI behavior.**

Run: `python C:\Users\chenlujie\.codex\skills\.system\skill-creator\scripts\quick_validate.py E:\tgbook\skills\tgbook-operate`

Expected: validation succeeds with a correctly named `SKILL.md` and required frontmatter.

Run: `python -m pytest tests/test_cli.py::test_login_required_stays_machine_readable -q`

Expected: PASS.

- [ ] **Step 5: Commit the operating skill.**

```bash
git add skills/tgbook-operate/SKILL.md tests/test_cli.py
git commit -m "feat: add tgbook agent operation skill"
```

### Task 7: Verify the Distribution and Perform Human Integration Checks

**Files:**
- Modify: `docs/superpowers/specs/2026-07-24-tgbook-design.md` only if implementation reveals an approved protocol deviation.

**Interfaces:**
- Verifies the package install, all tests, a real interactive login, page-one search, page-two search, and one document download.

- [ ] **Step 1: Install the package with test dependencies.**

Run: `python -m pip install -e ".[dev]"`

Expected: installation completes and `tgbook --help` exits with code `0`.

- [ ] **Step 2: Run static import and full test verification.**

Run: `python -m compileall -q src && python -m pytest -q`

Expected: both commands exit with code `0`.

- [ ] **Step 3: Perform the human-only login and private-chat smoke test using a real local configuration.**

Run: `tgbook login`

Expected: Telegram prompts for code and optional two-step password only in this command, then prints one JSON object with `ok: true` and a masked account.

Run: `tgbook search "麦肯锡思考工具" --page 1`

Expected: one JSON object with at least one `/book_` command and no non-JSON standard output.

Run: `tgbook search "麦肯锡思考工具" --page 2`

Expected: one JSON object from the page reached by clicking `(2) next »`.

Run: `$result = tgbook search "麦肯锡思考工具" --page 1 | ConvertFrom-Json; tgbook download $result.results[0].command --output .\manual-downloads`

Expected: one JSON object with `skipped: false`; repeat the exact command and expect `skipped: true` without a Telegram request.

- [ ] **Step 4: Commit only a specification adjustment if the actual bot protocol differs from the captured fixture.**

Run: `git status --short`

Expected: no credentials, sessions, books, indexes, locks, or downloads are tracked. If the bot's real output differs from the fixture, stop and obtain user approval for the specification change before adapting the parser and fixture.

## Plan Self-Review

Spec coverage is complete: Tasks 1 and 2 implement configuration, disk sessions, local index, and locking; Tasks 3 and 4 implement the observed bot format, private-chat-only transport, pagination, timeouts, media download, and Telegram error mapping; Task 5 implements the JSON/exit-code contract; Task 6 implements and validates the portable Agent skill; Task 7 covers package and real-bot verification. The plan contains no unresolved implementation marker and uses the same `AppConfig`, `AccountLock`, `DownloadIndex`, `BookBotService`, `TgbookError`, and error-code names throughout.
