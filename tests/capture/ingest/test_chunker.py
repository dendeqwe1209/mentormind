"""spec 02 FR-03/04/05, AC-05, AC-10 — RawDocument -> DocumentChunk."""

from __future__ import annotations

import re

from mentormind.capture.ingest.chunker import chunk_document
from mentormind.capture.ingest.raw import RawBlock, RawDocument
from mentormind.capture.ingest.tokens import WhitespaceTokenCounter
from mentormind.core.config import Settings
from mentormind.core.schemas import ChunkKind, DataClassification, DocumentChunk

DOC_ID = "DOC-0123456789ab"
COUNTER = WhitespaceTokenCounter()


def _settings(lo: int = 30, hi: int = 80, overlap: int = 10) -> Settings:
    return Settings(_env_file=None, chunk_min_tokens=lo, chunk_max_tokens=hi, chunk_overlap_tokens=overlap)


def _raw(blocks: list[RawBlock], extractor: str = "mmore") -> RawDocument:
    return RawDocument(
        path="data/samples/docs/x.pdf",
        title="X",
        num_pages=3,
        blocks=blocks,
        extractor=extractor,
    )


def _chunks(blocks: list[RawBlock], settings: Settings | None = None) -> list[DocumentChunk]:
    return chunk_document(
        _raw(blocks),
        doc_id=DOC_ID,
        classification=DataClassification.PUBLIC,
        counter=COUNTER,
        settings=settings or _settings(),
    )


def _sentences(n: int, prefix: str = "w") -> str:
    """n sentences of exactly 5 whitespace tokens each."""
    return " ".join(f"{prefix}{i} một hai ba bốn." for i in range(n))


def _table(rows: int, cols: int = 3) -> str:
    head = "| " + " | ".join(f"c{j}" for j in range(cols)) + " |"
    sep = "| " + " | ".join("---" for _ in range(cols)) + " |"
    body = ["| " + " | ".join(f"r{i}x{j}" for j in range(cols)) + " |" for i in range(rows)]
    return "\n".join([head, sep, *body])


def test_small_table_single_chunk_all_rows() -> None:
    out = _chunks([RawBlock(kind=ChunkKind.TABLE, text=_table(5), page=1)])
    assert len(out) == 1 and out[0].kind is ChunkKind.TABLE
    assert out[0].text.count("\n") + 1 == 7  # header + separator + 5 rows
    assert "table_part" not in out[0].metadata


def test_ac_10_large_table_split_with_repeated_header() -> None:
    out = _chunks([RawBlock(kind=ChunkKind.TABLE, text=_table(40), page=2)])
    assert len(out) > 1
    for i, chunk in enumerate(out, start=1):
        assert chunk.kind is ChunkKind.TABLE
        lines = chunk.text.splitlines()
        assert lines[0] == "| c0 | c1 | c2 |" and lines[1] == "| --- | --- | --- |"
        assert chunk.metadata["table_part"] == f"{i}/{len(out)}"
        assert COUNTER.count(chunk.text) <= 80
    rows = [ln for c in out for ln in c.text.splitlines()[2:]]
    assert rows == _table(40).splitlines()[2:]  # no row lost, none duplicated, order kept


def test_ac_10_table_with_a_caption_line_still_splits_into_valid_tables() -> None:
    # Docling prefixes some tables with their title (SQAM 2024, p.77): "TABLE 1 - ...\n\n| ...".
    caption = "TABLE 1 - SUPPLIER REACTION PLAN"
    out = _chunks([RawBlock(kind=ChunkKind.TABLE, text=f"{caption}\n\n{_table(40)}", page=2)])
    assert len(out) > 1
    for chunk in out:
        assert [ln for ln in chunk.text.splitlines() if ln.startswith("| ---")] == ["| --- | --- | --- |"]
    assert out[0].text.startswith(caption)
    assert all(caption not in c.text for c in out[1:])
    rows = [ln for c in out for ln in c.text.splitlines() if ln.startswith("| r")]
    assert rows == _table(40).splitlines()[2:]  # no row lost or duplicated


def test_oversize_table_row_kept_whole() -> None:
    huge = "| " + " ".join(f"t{i}" for i in range(200)) + " | y |"
    table = "| a | b |\n| --- | --- |\n" + huge
    out = _chunks([RawBlock(kind=ChunkKind.TABLE, text=table, page=1)])
    assert len(out) == 1 and huge in out[0].text


def test_table_not_merged_with_adjacent_text() -> None:
    out = _chunks(
        [
            RawBlock(kind=ChunkKind.TEXT, text="Trước bảng.", page=1),
            RawBlock(kind=ChunkKind.TABLE, text=_table(2), page=1),
            RawBlock(kind=ChunkKind.TEXT, text="Sau bảng.", page=1),
        ]
    )
    assert [c.kind for c in out] == [ChunkKind.TEXT, ChunkKind.TABLE, ChunkKind.TEXT]
    assert [c.text for c in out if c.kind is ChunkKind.TEXT] == ["Trước bảng.", "Sau bảng."]


def test_text_chunks_within_min_max() -> None:
    out = _chunks([RawBlock(kind=ChunkKind.TEXT, text="\n\n".join(_sentences(4) for _ in range(30)), page=1)])
    assert len(out) > 1
    for chunk in out:
        assert COUNTER.count(chunk.text) <= 80
    for chunk in out[:-1]:
        assert COUNTER.count(chunk.text) >= 30


def test_overlap_is_about_overlap_tokens() -> None:
    text = "\n\n".join(_sentences(4, prefix=f"p{k}_") for k in range(20))
    out = _chunks([RawBlock(kind=ChunkKind.TEXT, text=text, page=1)])
    assert len(out) > 2
    for prev, nxt in zip(out, out[1:], strict=False):
        words = nxt.text.split()
        shared = 0
        for k in range(1, min(len(prev.text.split()), len(words)) + 1):
            if prev.text.split()[-k:] == words[:k]:
                shared = k
        assert 0 < shared <= 10


def test_oversize_paragraph_split_by_sentence() -> None:
    para = _sentences(60)  # 300 tokens, one paragraph
    out = _chunks([RawBlock(kind=ChunkKind.TEXT, text=para, page=1)])
    assert len(out) > 1
    for chunk in out:
        assert COUNTER.count(chunk.text) <= 80
        assert chunk.text.rstrip().endswith(".")  # cut on a sentence boundary


def test_sentence_longer_than_max_is_windowed() -> None:
    out = _chunks([RawBlock(kind=ChunkKind.TEXT, text=" ".join(f"t{i}" for i in range(300)), page=1)])
    assert len(out) > 1
    assert all(COUNTER.count(c.text) <= 80 for c in out)


def test_figure_caption_not_merged_with_text() -> None:
    out = _chunks(
        [
            RawBlock(kind=ChunkKind.TEXT, text="Đoạn văn.", page=1),
            RawBlock(kind=ChunkKind.FIGURE_CAPTION, text="Hình 1: nhãn.", page=1),
        ]
    )
    assert [c.kind for c in out] == [ChunkKind.TEXT, ChunkKind.FIGURE_CAPTION]


def test_chunk_ids_are_sequential_per_page() -> None:
    out = _chunks(
        [
            RawBlock(kind=ChunkKind.TEXT, text="A.", page=1),
            RawBlock(kind=ChunkKind.TABLE, text=_table(1), page=1),
            RawBlock(kind=ChunkKind.TEXT, text="B.", page=2),
            RawBlock(kind=ChunkKind.TABLE, text=_table(1), page=2),
        ]
    )
    assert [c.chunk_id for c in out] == [f"{DOC_ID}#p1-0", f"{DOC_ID}#p1-1", f"{DOC_ID}#p2-0", f"{DOC_ID}#p2-1"]
    assert all(re.match(r"^DOC-[0-9a-f]{12}#p\d+-\d+$", c.chunk_id) for c in out)


def test_page_none_uses_zero_in_chunk_id() -> None:
    out = _chunks([RawBlock(kind=ChunkKind.TEXT, text="A.", page=None)])
    assert out[0].page is None and out[0].chunk_id == f"{DOC_ID}#p0-0"


def test_chunking_is_deterministic() -> None:
    blocks = [
        RawBlock(kind=ChunkKind.TEXT, text="\n\n".join(_sentences(4) for _ in range(30)), page=1),
        RawBlock(kind=ChunkKind.TABLE, text=_table(40), page=2),
    ]
    assert _chunks(blocks) == _chunks(blocks)


def test_ac_05_classification_propagates() -> None:
    out = chunk_document(
        _raw([RawBlock(kind=ChunkKind.TEXT, text="A.", page=1)]),
        doc_id=DOC_ID,
        classification=DataClassification.FACTORY_CONFIDENTIAL,
        counter=COUNTER,
        settings=_settings(),
    )
    assert out[0].data_classification is DataClassification.FACTORY_CONFIDENTIAL


def test_entities_metadata_and_provenance_filled() -> None:
    raw = _raw(
        [RawBlock(kind=ChunkKind.TEXT, text="PACK01 dùng AA123456-7890.", page=1, heading="Đóng gói")],
        extractor="docling",
    )
    [chunk] = chunk_document(
        raw, doc_id=DOC_ID, classification=DataClassification.SYNTHETIC, counter=COUNTER, settings=_settings()
    )
    assert chunk.process_ids == ["PACK01"] and chunk.part_numbers == ["AA123456-7890"]
    assert chunk.extractor == "docling" and chunk.title == "X" and chunk.source_path == raw.path
    assert chunk.metadata["heading"] == "Đóng gói"


def test_blank_blocks_skipped() -> None:
    assert _chunks([RawBlock(kind=ChunkKind.TEXT, text="  \n\n ", page=1)]) == []
