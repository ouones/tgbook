"""Tests for the book bot protocol service."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def test_search_restarts_at_page_one_then_clicks_next_for_page_two(fake_gateway, load_fixture):
    from tgbook.book_bot import BookBotService

    fake_gateway.queue_search_page(load_fixture("search-page-1.txt"), [[("- 1 -", "- 1 -"), ("next_2", "(2) next »")]])
    fake_gateway.queue_edit(load_fixture("search-page-2.txt"), [["prev_1", "« prev (1)"], ("- 2 -", "- 2 -")])
    service = BookBotService(fake_gateway)

    results = await service.search("麦肯锡思考工具", page=2)

    assert fake_gateway.sent_text == ["麦肯锡思考工具"]
    # Should have clicked the next button on the first response
    assert len(fake_gateway.clicked) >= 1
    assert results[0].command.startswith("/book_")


async def test_download_waits_for_document_and_moves_the_completed_file(fake_gateway, tmp_path):
    from tgbook.book_bot import BookBotService

    fake_gateway.queue_text("📚 麦肯锡思考工具")
    fake_gateway.queue_document("book.epub", b"book")

    downloaded = await BookBotService(fake_gateway).download("/book_aQRMmmPnZRV", tmp_path)

    assert downloaded.path == tmp_path / "book.epub"
    assert downloaded.path.read_bytes() == b"book"


async def test_search_with_single_page_returns_results(fake_gateway, load_fixture):
    from tgbook.book_bot import BookBotService

    fake_gateway.queue_search_page(load_fixture("search-page-1.txt"), [[("- 1 -", "- 1 -"), ("next_2", "(2) next »")]])
    service = BookBotService(fake_gateway)

    results = await service.search("麦肯锡思考工具", page=1)

    assert len(results) == 2
    assert results[0].command == "/book_a8vlLB0g8ve"
    assert results[0].title == "麦肯锡思考工具（独家首发）"


async def test_download_skips_when_file_exists(fake_gateway, tmp_path):
    from tgbook.book_bot import BookBotService

    existing = tmp_path / "book.epub"
    existing.write_bytes(b"existing")
    fake_gateway.queue_text("📚 some book")
    fake_gateway.queue_document("book.epub", b"new")

    downloaded = await BookBotService(fake_gateway).download("/book_123", tmp_path)

    assert downloaded.skipped is True
    assert downloaded.path == existing
