"""Fixed book-bot search result and pagination parser.

Parses the exact format shown in the Telegram capture fixture.
No support for arbitrary bot schemas or user-configurable selectors.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from tgbook.models import BookResult, ButtonRef

# Matches /book_<opaque-id> (format, human-size) at end of a line
COMMAND_LINE = re.compile(
    r"^(?P<command>/book_[A-Za-z0-9_]+)\s*\((?P<format>[^,()]+),\s*(?P<size>[^()]+)\)$",
    re.MULTILINE,
)

# Matches the "(N) next »" inline button pattern
NEXT_BUTTON = re.compile(r"^\(\d+\)\s+next\s+»$", re.IGNORECASE)


def parse_search_page(text: str) -> list[BookResult]:
    """Extract book results from a bot search response.

    For each /book_xxx command, finds the preceding 📚 marker and derives
    title and author from the text between the marker and the command.

    Args:
        text: The raw text of the bot's search response message.

    Returns:
        List of BookResult, one per /book_xxx command found.
    """
    results: list[BookResult] = []
    for match in COMMAND_LINE.finditer(text):
        marker = text.rfind("📚", 0, match.start())
        if marker < 0:
            continue
        # Extract lines between the 📚 marker and the command line
        lines = [
            line.strip()
            for line in text[marker + 1 : match.start()].splitlines()
            if line.strip()
        ]
        title = lines[0].removeprefix("📚  ").strip() if lines else None

        # Author is the first remaining line that's not Year/🌐/command
        author = None
        for line in lines[1:]:
            if not line.startswith(("Year:", "🌐", "/book_")):
                author = line
                break

        results.append(
            BookResult(
                command=match["command"],
                title=title,
                author=author,
                format=match["format"].lower(),
                size=match["size"],
            )
        )
    return results


def find_next_button(
    rows: Sequence[Sequence[tuple[object, str]]],
) -> ButtonRef | None:
    """Find the '(N) next »' inline keyboard button.

    Returns the row/column of the exactly-one next-page button.
    Returns None if no match or multiple matches (both are protocol errors
    handled by the caller).

    Args:
        rows: Inline keyboard button layout, each row is a sequence of
              (callback_data, text) tuples.

    Returns:
        ButtonRef with row and column, or None.
    """
    found: ButtonRef | None = None
    for row_idx, row in enumerate(rows):
        for col_idx, (_, text) in enumerate(row):
            if NEXT_BUTTON.match(text):
                if found is not None:
                    # Multiple next buttons — protocol error
                    return None
                found = ButtonRef(row=row_idx, column=col_idx)
    return found
