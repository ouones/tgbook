"""Fixed book-bot search result and pagination parser.

Parses the exact format shown in the Telegram capture fixture.
No support for arbitrary bot schemas or user-configurable selectors.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from tgbook.models import BookResult, ButtonRef

# Matches /book_<opaque-id> (format, human-size) — bot may append ↗️ suffix
COMMAND_LINE = re.compile(
    r"(?P<command>/book_[A-Za-z0-9_]+)\s*\((?P<format>[^,()]+),\s*(?P<size>[^()]+)\)",
)

# Matches the "(N) next »" inline button pattern
NEXT_BUTTON = re.compile(r"^\(\d+\)\s+next\s+»$", re.IGNORECASE)

# Splits entries at 📚 that starts a line (each line-starting 📚 marks a new book)
ENTRY_SPLIT = re.compile(r"\n(?=📚 )")


def parse_search_page(text: str) -> list[BookResult]:
    """Extract book results from a bot search response.

    Splits text at 📚 markers that start new book entries, then for each
    block finds the /book_xxx command and derives title/author from the
    preceding lines.

    Args:
        text: The raw text of the bot's search response message.

    Returns:
        List of BookResult, one per /book_xxx command found.
    """
    results: list[BookResult] = []
    blocks = ENTRY_SPLIT.split(text)

    for block in blocks:
        cmd_match = COMMAND_LINE.search(block)
        if not cmd_match:
            continue

        # Lines before the command match hold title, author, Year, 🌐
        prefix = block[: cmd_match.start()]
        lines = [line.strip() for line in prefix.splitlines() if line.strip()]

        if not lines:
            continue

        # First line is "📚 <title>"
        title = lines[0]
        if title.startswith("📚 "):
            title = title[2:].strip()
        elif title == "📚" and len(lines) > 1:
            title = lines[1]

        # Author is the first remaining line that is not Year, 🌐, command, or
        # pagination navigation (e.g. "(N) next »")
        author = None
        for idx in range(1, len(lines)):
            line = lines[idx]
            if line.startswith(("Year:", "🌐", "/book_")):
                continue
            # Skip navigation / button markers
            if re.match(r"^[\(«]", line):
                continue
            # If we hit another 📚 entry, stop
            if line.startswith("📚"):
                break
            author = line
            break

        results.append(
            BookResult(
                command=cmd_match["command"],
                title=title if title else None,
                author=author if author else None,
                format=cmd_match["format"].lower(),
                size=cmd_match["size"],
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
