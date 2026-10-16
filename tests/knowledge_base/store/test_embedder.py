"""spec 02 FR-07 — bge-m3 embedder: batching, normalisation, errors (model injected, no download)."""

from __future__ import annotations

import math
import os

import pytest

from mentormind.core.config import Settings
from mentormind.knowledge_base.store.embedder import BgeM3Embedder
from mentormind.knowledge_base.store.vector_store import VectorStoreError, get_vector_store


def _forward(vectors_by_text: dict[str, list[float]], calls: list[list[str]] | None = None):
    def forward(texts: list[str]) -> list[list[float]]:
        if calls is not None:
            calls.append(list(texts))
        return [vectors_by_text[t] for t in texts]

    return forward


def test_vectors_are_l2_normalised() -> None:
    emb = BgeM3Embedder(dim=2, forward=_forward({"a": [3.0, 4.0]}))
    [v] = emb.embed(["a"])
    assert v == pytest.approx([0.6, 0.8]) and math.isclose(sum(x * x for x in v), 1.0)


def test_order_is_preserved_and_batches_are_bounded() -> None:
    calls: list[list[str]] = []
    texts = [str(i) for i in range(5)]
    emb = BgeM3Embedder(dim=1, batch_size=2, forward=_forward({t: [float(i + 1)] for i, t in enumerate(texts)}, calls))
    out = emb.embed(texts)
    assert calls == [["0", "1"], ["2", "3"], ["4"]] and len(out) == 5


def test_empty_input_never_loads_the_model() -> None:
    def boom(texts: list[str]) -> list[list[float]]:
        raise AssertionError("must not be called")

    assert BgeM3Embedder(dim=4, forward=boom).embed([]) == []


def test_zero_vector_is_returned_as_is_not_divided() -> None:
    assert BgeM3Embedder(dim=2, forward=_forward({"a": [0.0, 0.0]})).embed(["a"]) == [[0.0, 0.0]]


def test_wrong_model_dimension_is_a_clear_error() -> None:
    emb = BgeM3Embedder(dim=1024, forward=_forward({"a": [1.0, 2.0]}))
    with pytest.raises(VectorStoreError, match=r"2 chiều.*1024"):
        emb.embed(["a"])


def test_dim_property_and_batch_size_validation() -> None:
    assert BgeM3Embedder(dim=1024, forward=_forward({})).dim == 1024
    with pytest.raises(ValueError, match="batch_size"):
        BgeM3Embedder(dim=4, batch_size=0)


def test_factory_builds_bge_m3_for_pgvector_without_loading_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from mentormind.knowledge_base.store import pgvector_store

    seen: list[object] = []
    monkeypatch.setattr(
        pgvector_store.PgVectorStore, "__init__", lambda self, dsn, table, embedder, **kw: seen.append(embedder)
    )
    get_vector_store(Settings(_env_file=None, vector_backend="pgvector", embedder="bge-m3"))
    assert isinstance(seen[0], BgeM3Embedder) and seen[0].dim == 1024


@pytest.mark.skipif(
    os.environ.get("KNOWHOW_RUN_SLOW") != "1", reason="downloads bge-m3 (~2.2 GB); set KNOWHOW_RUN_SLOW=1"
)
def test_real_bge_m3_ranks_by_meaning_across_languages() -> None:
    emb = BgeM3Embedder()
    query, near, far = emb.embed(
        [
            "kiểm tra nhãn trước khi đóng hộp",
            "Đối chiếu lot ID, part code và nhãn hộp trước khi bắt đầu.",
            "Nhiệt độ hàn mạch phải giữ dưới 260 độ.",
        ]
    )
    assert len(query) == 1024
    cos = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))  # noqa: E731
    assert cos(query, near) > cos(query, far)
