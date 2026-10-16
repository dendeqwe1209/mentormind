"""RawDocument -> DocumentChunk (spec 02 FR-03/04/05, 02b §4.3).

Deterministic: same input, same chunks, same ids (spec 02 FR-06).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from mentormind.capture.ingest.entities import compile_regex, find_part_numbers, find_process_ids
from mentormind.capture.ingest.raw import RawBlock, RawDocument
from mentormind.capture.ingest.tokens import TokenCounter
from mentormind.core.config import Settings
from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+")


@dataclass
class _Unit:
    """A piece of text that fits in one chunk; ``sep`` joins it to the previous unit."""

    text: str
    sep: str
    page: int | None
    heading: str | None
    overlap: bool = False


@dataclass
class _Pending:
    kind: ChunkKind
    text: str
    page: int | None
    heading: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_document(
    raw: RawDocument,
    *,
    doc_id: str,
    classification: DataClassification,
    counter: TokenCounter,
    settings: Settings,
) -> list[DocumentChunk]:
    """Split ``raw`` into chunks of at most ``settings.chunk_max_tokens`` tokens.

    Tables are never merged with text: a table is one chunk, or several (header repeated,
    ``metadata["table_part"] = "i/n"``) when it exceeds the maximum.

    Raises:
        ValueError: the overlap does not leave room for text, or a configured regex is invalid.
    """
    maximum, overlap = settings.chunk_max_tokens, settings.chunk_overlap_tokens
    if not 0 <= overlap < maximum:
        raise ValueError(f"chunk_overlap_tokens ({overlap}) phải nhỏ hơn chunk_max_tokens ({maximum}).")
    process_pattern = compile_regex(settings.process_id_regex, "process_id_regex")
    part_pattern = compile_regex(settings.part_number_regex, "part_number_regex")

    pending: list[_Pending] = []
    run: list[RawBlock] = []

    def flush_run() -> None:
        if run:
            pending.extend(_chunk_text_run(run, counter, maximum, overlap))
            run.clear()

    for block in raw.blocks:
        if not block.text.strip():
            continue
        if block.kind is ChunkKind.TABLE:
            flush_run()
            pending.extend(_chunk_table(block, counter, maximum))
        else:
            if run and run[0].kind is not block.kind:
                flush_run()
            run.append(block)
    flush_run()

    next_index: dict[int | None, int] = defaultdict(int)
    chunks: list[DocumentChunk] = []
    for item in pending:
        index = next_index[item.page]
        next_index[item.page] += 1
        metadata = dict(item.metadata)
        if item.heading is not None:
            metadata["heading"] = item.heading
        chunks.append(
            DocumentChunk(
                chunk_id=f"{doc_id}#p{item.page or 0}-{index}",
                doc_id=doc_id,
                source_path=raw.path,
                title=raw.title,
                page=item.page,
                kind=item.kind,
                text=item.text,
                process_ids=find_process_ids(item.text, process_pattern, settings.process_id_stoplist),
                part_numbers=find_part_numbers(item.text, part_pattern),
                data_classification=classification,
                extractor=raw.extractor,
                metadata=metadata,
            )
        )
    return chunks


def _chunk_table(block: RawBlock, counter: TokenCounter, maximum: int) -> list[_Pending]:
    text = block.text.strip()
    lines = text.splitlines()
    if counter.count(text) <= maximum or len(lines) < 3:
        return [_Pending(ChunkKind.TABLE, text, block.page, block.heading)]

    # Docling may put the table's title before the first "|" row; it stays with part 1 only.
    first = next((i for i, line in enumerate(lines) if line.lstrip().startswith("|")), None)
    if first is None or len(lines) - first < 3:
        return [_Pending(ChunkKind.TABLE, text, block.page, block.heading)]
    preamble = "\n".join(lines[:first]).strip()
    header = "\n".join(lines[first : first + 2])
    header_tokens = counter.count(header)
    parts: list[list[str]] = []
    rows: list[str] = []
    used = header_tokens + (counter.count(preamble) if preamble else 0)
    for row in lines[first + 2 :]:
        tokens = counter.count(row)
        if rows and used + tokens > maximum:
            parts.append(rows)
            rows, used = [], header_tokens
        rows.append(row)
        used += tokens
    parts.append(rows)  # a row longer than the maximum stays whole: never cut a cell
    return [
        _Pending(
            ChunkKind.TABLE,
            "\n".join([*([preamble, ""] if preamble and i == 1 else []), header, *part]),
            block.page,
            block.heading,
            {"table_part": f"{i}/{len(parts)}"},
        )
        for i, part in enumerate(parts, start=1)
    ]


def _chunk_text_run(blocks: list[RawBlock], counter: TokenCounter, maximum: int, overlap: int) -> list[_Pending]:
    """Greedy-pack consecutive same-kind blocks; each chunk after the first starts with a tail."""
    kind = blocks[0].kind
    limit = maximum - overlap  # a unit always fits next to a full-size tail
    units = [u for block in blocks for u in _units(block, counter, limit)]

    out: list[_Pending] = []
    buf: list[_Unit] = []
    used = 0

    def flush() -> None:
        nonlocal buf, used
        real = [u for u in buf if not u.overlap]
        if not real:
            return
        text = _join(buf)
        out.append(_Pending(kind, text, real[0].page, real[0].heading))
        tail = _tail(text, counter, overlap)
        buf = [_Unit(tail, " ", real[0].page, None, overlap=True)] if tail else []
        used = counter.count(tail) if tail else 0

    for unit in units:
        tokens = counter.count(unit.text)
        if any(not u.overlap for u in buf) and used + tokens > maximum:
            flush()
        buf.append(unit)
        used += tokens
    flush()
    return out


def _join(units: list[_Unit]) -> str:
    return "".join(u.text if i == 0 else u.sep + u.text for i, u in enumerate(units))


def _units(block: RawBlock, counter: TokenCounter, limit: int) -> list[_Unit]:
    units: list[_Unit] = []
    for paragraph in (p.strip() for p in _PARAGRAPH_BREAK.split(block.text)):
        if not paragraph:
            continue
        pieces = [paragraph] if counter.count(paragraph) <= limit else _split_long(paragraph, counter, limit)
        for i, piece in enumerate(pieces):
            units.append(_Unit(piece, "\n\n" if i == 0 else " ", block.page, block.heading))
    return units


def _split_long(paragraph: str, counter: TokenCounter, limit: int) -> list[str]:
    """Pack sentences up to ``limit``; a sentence over ``limit`` falls back to word windows."""
    pieces: list[str] = []
    current: list[str] = []
    used = 0
    for sentence in _SENTENCE_END.split(paragraph):
        for part in _word_windows(sentence, counter, limit):
            tokens = counter.count(part)
            if current and used + tokens > limit:
                pieces.append(" ".join(current))
                current, used = [], 0
            current.append(part)
            used += tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def _word_windows(sentence: str, counter: TokenCounter, limit: int) -> list[str]:
    if counter.count(sentence) <= limit:
        return [sentence]
    windows: list[str] = []
    current: list[str] = []
    used = 0
    for word in sentence.split():
        tokens = counter.count(word)
        if current and used + tokens > limit:
            windows.append(" ".join(current))
            current, used = [], 0
        current.append(word)
        used += tokens
    if current:
        windows.append(" ".join(current))
    return windows


def _tail(text: str, counter: TokenCounter, overlap: int) -> str:
    """The last whole sentences of ``text`` worth at most ``overlap`` tokens (words if none fit)."""
    if overlap <= 0 or counter.count(text) <= overlap:
        return ""
    starts = [0] + [m.end() for m in _SENTENCE_END.finditer(text)]
    for start in starts[1:]:  # earliest start that fits = longest whole-sentence tail
        if counter.count(text[start:]) <= overlap:
            return text[start:]
    words = text.split()
    tail_words: list[str] = []
    used = 0
    for word in reversed(words):
        tokens = counter.count(word)
        if used + tokens > overlap:
            break
        tail_words.append(word)
        used += tokens
    return " ".join(reversed(tail_words))
