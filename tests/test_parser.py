"""Tests for the fixed book-bot search and pagination parser."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def load_fixture():
    def _load(name: str) -> str:
        fixture_path = Path(__file__).parent / "fixtures" / name
        return fixture_path.read_text(encoding="utf-8")
    return _load


def test_parse_search_page_extracts_the_stable_command_and_metadata(load_fixture):
    from tgbook.parser import parse_search_page
    from tgbook.models import BookResult

    results = parse_search_page(load_fixture("search-page-1.txt"))

    assert len(results) == 2
    assert results[0] == BookResult(
        command="/book_a8vlLB0g8ve",
        title="麦肯锡思考工具（独家首发）",
        author=None,
        format="epub",
        size="163 KB",
    )
    assert results[1] == BookResult(
        command="/book_bCw9lUDSkwF",
        title="麦肯锡逻辑思考法",
        author="Author: 照屋华子",
        format="pdf",
        size="42.5 MB",
    )


def test_parse_search_page_returns_empty_for_no_commands():
    from tgbook.parser import parse_search_page

    assert parse_search_page("No results found.") == []


def test_next_button_requires_the_captured_page_control():
    from tgbook.parser import find_next_button
    from tgbook.models import ButtonRef

    assert find_next_button([[(None, "- 1 -"), (None, "(2) next »")]]) == ButtonRef(0, 1)
    assert find_next_button([[(None, "- 1 -")]]) is None
    assert find_next_button([]) is None


def test_next_button_returns_none_for_ambiguous_matches():
    from tgbook.parser import find_next_button

    # Multiple next buttons should not happen in the fixed protocol
    assert find_next_button([[(None, "(2) next »"), (None, "(3) next »")]]) is None
