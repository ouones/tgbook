"""Tests for account locking and download index persistence."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


LOCK_PROBE = """
import sys
from pathlib import Path
from tgbook.state import AccountLock
try:
    lock = AccountLock(Path(sys.argv[1]))
    lock.acquire()
    print("acquired")
    lock.release()
except Exception as e:
    print(f"error: {e}")
    sys.exit(getattr(e, 'code', None) and 4 or 1)
"""


def test_index_returns_only_an_existing_file(tmp_path):
    from tgbook.state import DownloadIndex

    index = DownloadIndex(tmp_path / "download-index.json")
    output = tmp_path / "book.epub"
    output.write_bytes(b"book")
    index.record("/book_123", output)

    assert index.lookup("/book_123") == output.resolve()
    output.unlink()
    assert index.lookup("/book_123") is None
    assert "/book_123" not in json.loads(index.path.read_text(encoding="utf-8"))


def test_index_records_absolute_paths(tmp_path):
    from tgbook.state import DownloadIndex

    index = DownloadIndex(tmp_path / "download-index.json")
    output = tmp_path / "subdir" / "book.epub"
    output.parent.mkdir()
    output.write_bytes(b"content")
    index.record("/book_456", output)

    assert index.lookup("/book_456") == output.resolve()


def test_index_discard_removes_entry(tmp_path):
    from tgbook.state import DownloadIndex

    index = DownloadIndex(tmp_path / "download-index.json")
    output = tmp_path / "book.epub"
    output.write_bytes(b"book")
    index.record("/book_123", output)
    index.record("/book_456", output)

    index.discard("/book_123")
    assert index.lookup("/book_123") is None
    assert index.lookup("/book_456") == output.resolve()


def test_index_handles_missing_file_gracefully(tmp_path):
    from tgbook.state import DownloadIndex

    index = DownloadIndex(tmp_path / "nonexistent" / "download-index.json")
    assert index.lookup("/book_123") is None


def test_second_process_cannot_acquire_account_lock(tmp_path):
    from tgbook.state import AccountLock

    lock = AccountLock(tmp_path / "phone.lock")
    lock.acquire()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", LOCK_PROBE, str(lock.path)],
            capture_output=True,
            text=True,
            check=False,
            env={"PYTHONPATH": str(Path(__file__).parent.parent / "src"), **{k: v for k, v in os.environ.items() if k != "PYTHONPATH"}},
        )
    finally:
        lock.release()

    assert completed.returncode == 4


def test_lock_acquire_release_cycle_works(tmp_path):
    from tgbook.state import AccountLock

    lock = AccountLock(tmp_path / "phone.lock")
    lock.acquire()
    lock.release()
    # Should be able to re-acquire after release
    lock.acquire()
    lock.release()
