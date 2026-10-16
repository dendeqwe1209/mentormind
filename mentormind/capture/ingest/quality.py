"""Spot mis-encoded text layers (spec 02 FR-02b).

A PDF whose font maps glyphs to the wrong code points still has plenty of "text", so the character
count cannot tell. Real Vietnamese, Japanese, English and technical text hardly ever contains the
IPA-extension and Greek letters such garbage is made of (``σϯιʔςΫχΧϧϨϏϡʔ``), so their share of the
letters on a page is the signal. It only flags: the pages are still chunked, and the run log says
which pages to look at.
"""

from __future__ import annotations

from collections import defaultdict

from mentormind.capture.ingest.raw import RawDocument

#: Fewer letters than this say nothing about a page.
MIN_LETTERS = 20


def _is_odd(char: str) -> bool:
    code = ord(char)
    return 0x0250 <= code <= 0x02FF or 0x0370 <= code <= 0x03FF


def odd_ratio(text: str) -> float:
    """Share of letters that are IPA-extension or Greek (0 when ``text`` has no letters)."""
    letters = [c for c in text if c.isalpha()]
    return sum(map(_is_odd, letters)) / len(letters) if letters else 0.0


def suspect_pages(raw: RawDocument, *, max_ratio: float) -> list[int]:
    """Page numbers (ascending) whose text has more than ``max_ratio`` odd letters."""
    by_page: dict[int, list[str]] = defaultdict(list)
    for block in raw.blocks:
        if block.page is not None:
            by_page[block.page].append(block.text)
    flagged = []
    for page, texts in sorted(by_page.items()):
        text = "\n".join(texts)
        if sum(c.isalpha() for c in text) >= MIN_LETTERS and odd_ratio(text) > max_ratio:
            flagged.append(page)
    return flagged
