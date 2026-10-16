"""Graph publication and evidence based retrieval without a database service."""

import os
import uuid
from contextlib import contextmanager
from typing import Any, cast

import pytest

from mentormind.core.config import Settings
from mentormind.core.providers.errors import InvalidJSONError, ProviderError
from mentormind.core.schemas import Evidence, ReviewInfo, WorkProfile
from mentormind.core.schemas.vector import VectorChunk, VectorHit
from mentormind.knowledge_base.kg.client import Neo4jGraph
from mentormind.knowledge_base.kg.loader import KnowledgeGraphLoader
from mentormind.knowledge_base.retrieval.hybrid import (
    TEMPLATES,
    HybridRetriever,
    Template,
    get_hybrid_retriever,
    token_cost,
)
from mentormind.knowledge_base.sigma.adapter import CsvSigmaAdapter
from mentormind.knowledge_base.store.vector_store import MemoryVectorStore


class RecordingGraph:
    def __init__(self):
        self.calls = []
        self.version = None
        self.rows = {}

    def run(self, query, **params):
        self.calls.append((query, params))
        if "RETURN s.version AS version" in query:
            return [] if self.version is None else [{"version": self.version}]
        for key, rows in self.rows.items():
            if key in query:
                return rows
        return []


class FixedVectors(MemoryVectorStore):
    """Returns fixed hits, so ranking can be checked against exact vector scores."""

    def __init__(self, hits):
        super().__init__()
        self.hits = hits

    def search(self, query, k=8, filters=None):
        return self.hits[:k]


def hit(ref_id, score, text=None):
    chunk = VectorChunk(
        chunk_id=ref_id,
        source_type="work_profile",
        ref_id=ref_id,
        text=text or f"Bước {ref_id}",
        data_classification="synthetic",
    )
    return VectorHit(chunk=chunk, score=score)


def write_sigma(directory):
    (directory / "lots.csv").write_text(
        "lot_id,product_code,process_id,date,shift,operator_id,qty\nLOT-1,P1,PACK01,2026-09-28,A,O1,10\n",
        encoding="utf-8",
    )
    (directory / "defects.csv").write_text(
        "defect_id,lot_id,process_id,defect_code,description,qty,detected_at\n"
        "DEF-1,LOT-1,PACK01,D-01,Thiếu linh kiện,2,2026-09-28T08:00:00\n",
        encoding="utf-8",
    )
    (directory / "defect_catalog.csv").write_text(
        "defect_code,symptom_name,known_root_cause_id,known_root_cause,prevention_profile_id\n"
        "D-01,Thiếu linh kiện,RC-01,Bỏ sót,WP-PACK01-005\n",
        encoding="utf-8",
    )


def profile(number=1, status="approved", version=1):
    return WorkProfile(
        schema_version="1.0",
        profile_id=f"WP-PACK01-{number:03d}",
        process_id="PACK01",
        step_order=number,
        step=f"Kiểm tra linh kiện bước {number}",
        hand_action="Cầm linh kiện",
        reason="Tránh trầy" if status == "approved" else None,
        reason_source="expert_verbal" if status == "approved" else None,
        evidence=Evidence(video_id="VID-1", t_start=2, t_end=4, segment_ids=["VID-1#s1"]),
        confidence=0.9,
        generated_by="human",
        data_classification="synthetic",
        status=status,
        review=ReviewInfo(reviewer="EXP-1", reviewed_at="2026-09-28T00:00:00Z") if status == "approved" else None,
        created_at="2026-09-28T00:00:00Z",
        version=version,
    )


def test_loader_publishes_only_approved_and_explicit_segment_ids():
    graph, vectors = RecordingGraph(), MemoryVectorStore()
    loader = KnowledgeGraphLoader(graph, vectors)
    result = loader.load_profiles([profile(), profile(2, "draft"), profile(3, "rejected")])
    assert result.loaded == 1 and result.skipped == 2
    assert [h.chunk.ref_id for h in vectors.search("Kiểm tra", filters={"source_type": "work_profile"})] == [
        "WP-PACK01-001"
    ]
    assert any("EVIDENCED_BY" in q and p.get("segment_ids") == ["VID-1#s1"] for q, p in graph.calls)
    assert any("EVIDENCED_BY" in q and "r.profile_t_start" in q and "v.t_start" not in q for q, _ in graph.calls)
    assert any("NEXT" in q for q, _ in graph.calls)


def test_stale_version_cannot_replace_published_profile():
    graph, vectors = RecordingGraph(), MemoryVectorStore()
    graph.version = 3
    result = KnowledgeGraphLoader(graph, vectors).load_profiles([profile(version=2)])
    assert result.stale == 1
    assert vectors.search("Kiểm tra") == []


def test_failed_vector_write_rolls_back_graph_publication():
    class TransactionalGraph(RecordingGraph):
        def __init__(self):
            super().__init__()
            self.steps = set()

        @contextmanager
        def transaction(self):
            before = self.steps.copy()
            try:
                yield
            except Exception:
                self.steps = before
                raise

        def run(self, query, **params):
            if "MERGE (s:Step" in query:
                self.steps.add(params["profile_id"])
            return super().run(query, **params)

    class FailingVectors(MemoryVectorStore):
        def upsert(self, chunks):
            raise RuntimeError("vector unavailable")

    graph = TransactionalGraph()
    with pytest.raises(RuntimeError, match="vector unavailable"):
        KnowledgeGraphLoader(graph, FailingVectors()).load_profiles([profile()])
    assert graph.steps == set()


def test_failed_graph_commit_removes_new_vector_chunk():
    class CommitFailGraph(RecordingGraph):
        @contextmanager
        def transaction(self):
            yield
            raise RuntimeError("commit failed")

    vectors = MemoryVectorStore()
    with pytest.raises(RuntimeError, match="commit failed"):
        KnowledgeGraphLoader(CommitFailGraph(), vectors).load_profiles([profile()])
    assert vectors.search("Kiểm tra") == []


def test_neo4j_client_uses_one_transaction_and_rolls_back_on_failure():
    class Transaction:
        def __init__(self):
            self.queries = []
            self.rolled_back = False

        def run(self, query, **params):
            self.queries.append(query)
            return []

        def rollback(self):
            self.rolled_back = True

    class Session:
        def __init__(self, transaction):
            self.transaction = transaction

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def begin_transaction(self):
            return self.transaction

        def run(self, query, **params):
            raise AssertionError("query escaped the transaction")

    class Driver:
        def __init__(self, session):
            self._session = session

        def session(self):
            return self._session

    transaction = Transaction()
    graph = Neo4jGraph.__new__(Neo4jGraph)
    graph._driver = cast(Any, Driver(Session(transaction)))
    graph._transaction = None
    with pytest.raises(RuntimeError, match="stop"):
        with graph.transaction():
            graph.run("MERGE (:Step {profile_id: $id})", id="WP-PACK01-001")
            raise RuntimeError("stop")
    assert transaction.queries == ["MERGE (:Step {profile_id: $id})"]
    assert transaction.rolled_back is True


def test_unload_removes_only_step_and_its_chunk():
    graph, vectors = RecordingGraph(), MemoryVectorStore()
    loader = KnowledgeGraphLoader(graph, vectors)
    loader.load_profiles([profile()])
    loader.unload_profile("WP-PACK01-001")
    assert vectors.search("Kiểm tra") == []
    assert any("DETACH DELETE s" in q for q, _ in graph.calls)
    assert not any("DELETE p" in q for q, _ in graph.calls)


def test_failed_vector_delete_rolls_back_graph_unload():
    class TransactionalGraph(RecordingGraph):
        def __init__(self):
            super().__init__()
            self.steps = set()

        @contextmanager
        def transaction(self):
            before = self.steps.copy()
            try:
                yield
            except Exception:
                self.steps = before
                raise

        def run(self, query, **params):
            if "MERGE (s:Step" in query:
                self.steps.add(params["profile_id"])
            if "DETACH DELETE s" in query:
                self.steps.discard(params["profile_id"])
                raise RuntimeError("graph delete failed")
            return super().run(query, **params)

    graph, vectors = TransactionalGraph(), MemoryVectorStore()
    loader = KnowledgeGraphLoader(graph, vectors)
    loader.load_profiles([profile()])
    with pytest.raises(RuntimeError, match="graph delete failed"):
        loader.unload_profile("WP-PACK01-001")
    assert graph.steps == {"WP-PACK01-001"}
    assert vectors.search("Kiểm tra")


def test_retrieval_keeps_passage_and_citation_together_and_filters_process():
    graph, vectors = RecordingGraph(), MemoryVectorStore()
    KnowledgeGraphLoader(graph, vectors).load_profiles([profile()])
    graph.rows["MATCH (s:Step {profile_id: $profile_id})"] = [
        {"fact": "Bước 1 dùng linh kiện A123", "source_type": "work_profile", "ref_id": "WP-PACK01-001"}
    ]
    result = HybridRetriever(vectors, graph).retrieve("linh kiện", process_id="PACK01")
    assert result.passages and result.graph_facts
    assert len(result.passages) == len(result.citations) == len(result.classifications)
    assert any(c.ref_id == "WP-PACK01-001" for c in result.citations)
    assert HybridRetriever(vectors, graph).retrieve("linh kiện", process_id="PACK02").passages == []


def test_video_expansion_citation_carries_profile_evidence_window():
    graph, vectors = RecordingGraph(), MemoryVectorStore()
    KnowledgeGraphLoader(graph, vectors).load_profiles([profile()])
    graph.rows["[r:EVIDENCED_BY]"] = [
        {
            "fact": "Video VID-1 đoạn VID-1#s1",
            "source_type": "video_segment",
            "ref_id": "VID-1#s1",
            "data_classification": "synthetic",
            "t_start": 2,
            "t_end": 4,
        }
    ]
    result = HybridRetriever(vectors, graph).retrieve("Kiểm tra")
    citation = next(c for c in result.citations if c.source_type == "video_segment")
    assert (citation.ref_id, citation.t_start, citation.t_end) == ("VID-1#s1", 2, 4)


def test_bad_router_output_falls_back_to_vector():
    graph, vectors = RecordingGraph(), MemoryVectorStore()
    KnowledgeGraphLoader(graph, vectors).load_profiles([profile()])

    class BadRouter:
        def generate_json(self, *args, **kwargs):
            return {"template": "MATCH (n) DETACH DELETE n"}

    result = HybridRetriever(vectors, graph, router=BadRouter()).retrieve("Kiểm tra")
    assert result.passages and all("DETACH DELETE n" not in q for q, _ in graph.calls)

    class InvalidJsonRouter:
        def generate_json(self, *args, **kwargs):
            raise InvalidJSONError("invalid", raw_text="not json")

    assert HybridRetriever(vectors, graph, router=InvalidJsonRouter()).retrieve("Kiểm tra").passages


def test_ac_10_unreachable_router_falls_back_to_vector():
    graph, vectors = RecordingGraph(), MemoryVectorStore()
    KnowledgeGraphLoader(graph, vectors).load_profiles([profile()])

    class DownRouter:
        def generate_json(self, *args, **kwargs):
            raise ProviderError("connection refused")

    assert HybridRetriever(vectors, graph, router=DownRouter()).retrieve("Kiểm tra").passages


def test_ac_10_symptom_text_is_escaped_for_the_fulltext_fallback():
    graph = RecordingGraph()
    graph.rows["MATCH (s:Symptom) RETURN"] = [{"symptom_id": "D-01", "name": "Thiếu linh kiện trong hộp"}]

    class Router:
        def generate_json(self, *args, **kwargs):
            return {"template": "where_symptom_occurred", "symptom_text": 'Móp/méo (góc) "AND'}

    HybridRetriever(MemoryVectorStore(), graph, router=Router()).retrieve("móp góc")
    fulltext = [params["text"] for query, params in graph.calls if "db.index.fulltext" in query]
    assert fulltext == [r"móp\/méo \(góc\) \"and"]


def test_passage_ranks_before_the_graph_facts_expanded_from_it():
    graph = RecordingGraph()
    fact = "Video VID-1 đoạn VID-1#s1"
    graph.rows["[r:EVIDENCED_BY]"] = [
        {"fact": fact, "source_type": "video_segment", "ref_id": "VID-1#s1", "data_classification": "synthetic"}
    ]
    passage = "Kiểm tra linh kiện bước 1 trước khi đóng nắp hộp carton theo chiều nghiêng"
    vectors = FixedVectors([hit("WP-PACK01-001", 0.03, passage)])
    assert HybridRetriever(vectors, graph).retrieve("Kiểm tra").passages == [passage, fact]
    # When the budget only fits one of them, the evidence itself is kept, not what it led to.
    tight = HybridRetriever(vectors, graph, token_budget=token_cost(passage))
    assert tight.retrieve("Kiểm tra").passages == [passage]


def test_vector_hit_reached_by_a_template_gets_the_graph_bonus():
    graph = RecordingGraph()
    graph.rows["toString(s.step_order)"] = [
        {
            "fact": "Bước 2: Đóng nắp",
            "source_type": "work_profile",
            "ref_id": "WP-PACK01-002",
            "data_classification": "synthetic",
        }
    ]

    class Router:
        def generate_json(self, *args, **kwargs):
            return {"template": "steps_of_process", "process_id": "PACK01"}

    vectors = FixedVectors([hit("WP-PACK01-001", 0.0328), hit("WP-PACK01-002", 0.0300)])
    context = HybridRetriever(vectors, graph, router=Router()).retrieve("Công đoạn PACK01 gồm những bước nào?")
    assert [c.ref_id for c in context.citations] == ["WP-PACK01-002", "WP-PACK01-002", "WP-PACK01-001"]
    assert context.passages[1] == "Bước 2: Đóng nắp"


def test_two_document_chunks_keep_distinct_passages_and_citations():
    vectors = MemoryVectorStore()
    vectors.upsert(
        [
            VectorChunk(
                chunk_id="DOC-1#1",
                source_type="document",
                ref_id="DOC-1",
                text="Kiểm tra góc vát",
                data_classification="synthetic",
            ),
            VectorChunk(
                chunk_id="DOC-1#2",
                source_type="document",
                ref_id="DOC-1",
                text="Kiểm tra bề mặt",
                data_classification="synthetic",
            ),
        ]
    )
    context = HybridRetriever(vectors, RecordingGraph()).retrieve("Kiểm tra", k=2)
    assert len(context.passages) == len(context.citations) == 2
    assert set(context.passages) == {"Kiểm tra góc vát", "Kiểm tra bề mặt"}


def test_accentless_symptom_lookup_and_template_is_parameterized():
    graph, vectors = RecordingGraph(), MemoryVectorStore()
    graph.rows["MATCH (s:Symptom) RETURN"] = [{"symptom_id": "D-01", "name": "Thiếu linh kiện trong hộp"}]
    graph.rows["HAS_DEFECT"] = [{"fact": "Lô LOT-1 có lỗi thiếu linh kiện", "source_type": "sigma", "ref_id": "LOT-1"}]

    class Router:
        def generate_json(self, *args, **kwargs):
            return {"template": "where_symptom_occurred", "symptom_text": "thieu linh kien"}

    result = HybridRetriever(vectors, graph, router=Router()).retrieve("thieu linh kien")
    assert any("LOT-1" in fact for fact in result.graph_facts)
    assert any(p.get("symptom_id") == "D-01" for _, p in graph.calls)


def test_root_cause_citation_identifies_catalog_row():
    assert "defect_catalog.csv#" in TEMPLATES["root_causes_of_symptom"]


def test_sigma_csv_loads_lot_defect_and_prevention_without_unapproved_step(tmp_path):
    write_sigma(tmp_path)
    graph = RecordingGraph()
    assert KnowledgeGraphLoader(graph, MemoryVectorStore()).load_sigma(CsvSigmaAdapter(tmp_path)) == 1
    assert any("HAS_DEFECT" in q and p.get("symptom_id") == "D-01" for q, p in graph.calls)
    assert any("PREVENTED_BY" in q and p.get("profile_id") == "WP-PACK01-005" for q, p in graph.calls)


def test_ac_11_sigma_records_carry_the_label_they_were_loaded_with(tmp_path):
    write_sigma(tmp_path)

    def labels_written(*classification):
        graph = RecordingGraph()
        KnowledgeGraphLoader(graph, MemoryVectorStore()).load_sigma(CsvSigmaAdapter(tmp_path), *classification)
        writes = [(q, p) for q, p in graph.calls if "MERGE (l:Lot" in q or "MERGE (s:Symptom" in q]
        assert len(writes) == 3 and all("data_classification = $classification" in q for q, _ in writes)
        return {p["classification"] for _, p in writes}

    assert labels_written("synthetic") == {"synthetic"}
    assert labels_written() == {"factory_confidential"}


def test_ac_11_sigma_fact_takes_the_strictest_label_of_its_parts():
    assert "'synthetic'" not in "".join(TEMPLATES.values())
    graph = RecordingGraph()
    graph.rows["l.lot_id AS ref_id"] = [
        {
            "fact": "Lô LOT-1 tại PACK01 có lỗi Thiếu linh kiện",
            "source_type": "sigma",
            "ref_id": "LOT-1",
            "data_classification": ["synthetic", "synthetic", "synthetic"],
        },
        {
            "fact": "Lô LOT-2 tại PACK01 có lỗi Thiếu linh kiện",
            "source_type": "sigma",
            "ref_id": "LOT-2",
            "data_classification": ["synthetic", None, "synthetic"],
        },
    ]

    class Router:
        def generate_json(self, *args, **kwargs):
            return {"template": "where_symptom_occurred", "defect_code": "D-01"}

    context = HybridRetriever(MemoryVectorStore(), graph, router=Router()).retrieve("Lỗi thiếu linh kiện ở lô nào?")
    labels = {c.ref_id: label for c, label in zip(context.citations, context.classifications, strict=True)}
    assert labels == {"LOT-1": "synthetic", "LOT-2": "factory_confidential"}


def test_committed_sigma_fixture_is_case_and_time_linkable():
    from pathlib import Path

    adapter = CsvSigmaAdapter(Path(__file__).resolve().parents[2] / "data" / "mock_sigma")
    lots = {lot.lot_id: lot for lot in adapter.list_lots()}
    codes = {item.defect_code for item in adapter.defect_catalog()}
    defects = adapter.list_defects()
    assert len(lots) == 6 and len(codes) == 6 and len(defects) == 6
    for defect in defects:
        lot = lots[defect.lot_id]
        assert defect.defect_code in codes
        assert defect.process_id == lot.process_id
        assert defect.detected_at.date() == lot.date
        assert 6 <= defect.detected_at.hour < 14


def test_retriever_factory_needs_no_cloud_key_for_offline_retrieval():
    settings = Settings(_env_file=None, vector_backend="memory", llm_provider="qwen_api", llm_api_key=None)
    retriever = get_hybrid_retriever(settings)
    assert retriever.router is None
    retriever.close()


@pytest.mark.integration
def test_neo4j_profile_lifecycle_and_all_six_templates(tmp_path):
    uri = os.getenv("KNOWHOW_TEST_NEO4J_URI")
    if not uri:
        pytest.skip("Set KNOWHOW_TEST_NEO4J_URI to run against a disposable Neo4j 5 instance")
    token = "IT" + uuid.uuid4().hex[:8].upper()
    settings = Settings(
        _env_file=None, neo4j_uri=uri, neo4j_password=os.getenv("KNOWHOW_TEST_NEO4J_PASSWORD", "change-me")
    )
    graph = Neo4jGraph(settings)
    try:
        graph.init()
        vectors = MemoryVectorStore()
        loader = KnowledgeGraphLoader(graph, vectors)
        profiles = [
            profile(i).model_copy(
                update={
                    "profile_id": f"WP-{token}-{i:03d}",
                    "process_id": token,
                    "part_numbers": [f"{token}-PART"] if i == 2 else [],
                    "evidence": Evidence(
                        video_id=f"{token}-VID", t_start=i, t_end=i + 1, segment_ids=[f"{token}-VID#s{i}"]
                    ),
                }
            )
            for i in (1, 2, 3)
        ]
        other = [
            profile(i, status).model_copy(update={"profile_id": f"WP-{token}-{i:03d}", "process_id": token})
            for i, status in ((4, "draft"), (5, "rejected"))
        ]
        result = loader.load_profiles(profiles + other)
        assert (result.loaded, result.skipped) == (3, 2)
        assert loader.stats()["Step"] >= 3
        assert loader.load_profiles(profiles).loaded == 3
        assert (
            len(
                graph.run(
                    "MATCH (p:Process {process_id: $pid})-[:HAS_STEP]->(s:Step) RETURN s.profile_id AS id", pid=token
                )
            )
            == 3
        )
        edges = graph.run(
            "MATCH (a:Step)-[:NEXT]->(b:Step) "
            "WHERE a.profile_id STARTS WITH $prefix "
            "RETURN a.step_order AS a, b.step_order AS b",
            prefix=f"WP-{token}",
        )
        assert [(row["a"], row["b"]) for row in edges] == [(1, 2), (2, 3)]

        (tmp_path / "lots.csv").write_text(
            f"lot_id,product_code,process_id,date,shift,operator_id,qty\n{token}-LOT,P1,{token},2026-09-28,A,O1,10\n",
            encoding="utf-8",
        )
        (tmp_path / "defects.csv").write_text(
            "defect_id,lot_id,process_id,defect_code,description,qty,detected_at\n"
            f"{token}-DEF,{token}-LOT,{token},{token}-D01,Lỗi,1,2026-09-28T08:00:00\n",
            encoding="utf-8",
        )
        (tmp_path / "defect_catalog.csv").write_text(
            "defect_code,symptom_name,known_root_cause_id,known_root_cause,prevention_profile_id\n"
            f"{token}-D01,Thiếu linh kiện,{token}-RC,Bỏ sót,WP-{token}-002\n",
            encoding="utf-8",
        )
        loader.load_sigma(CsvSigmaAdapter(tmp_path), "synthetic")
        retriever = HybridRetriever(vectors, graph)
        lots = retriever.run_template("where_symptom_occurred", symptom_id=f"{token}-D01", process_id=token)
        assert [row["data_classification"] for row in lots] == [["synthetic"] * 3]
        retriever.match_symptom('zzz (móp/méo) "AND')  # Lucene syntax must not break the fallback
        expected = {
            "steps_of_process": (dict(process_id=token), "WP-"),
            "steps_using_part": (dict(part_number=f"{token}-PART", process_id=token), "WP-"),
            "where_symptom_occurred": (dict(symptom_id=f"{token}-D01", process_id=token), "-LOT"),
            "root_causes_of_symptom": (dict(symptom_id=f"{token}-D01", process_id=token), "Bỏ sót"),
            "prevention_steps": (dict(symptom_id=f"{token}-D01", process_id=token), "WP-"),
            "lots_with_defect": (
                dict(symptom_id=f"{token}-D01", process_id=token, date_from="2026-09-28", date_to="2026-09-28"),
                "-LOT",
            ),
        }
        for name, (params, fragment) in expected.items():
            rows = retriever.run_template(cast(Template, name), **params)
            assert rows and any(fragment in row["fact"] or fragment in row["ref_id"] for row in rows)

        loader.unload_profile(f"WP-{token}-002")
        assert retriever.run_template("steps_using_part", part_number=f"{token}-PART") == []
        assert graph.run("MATCH (p:Part {part_number: $number}) RETURN p.part_number AS number", number=f"{token}-PART")
    finally:
        for label, key in (
            ("Process", "process_id"),
            ("Step", "profile_id"),
            ("Exception", "exception_id"),
            ("Part", "part_number"),
            ("VideoSegment", "segment_id"),
            ("Symptom", "symptom_id"),
            ("RootCause", "cause_id"),
            ("Lot", "lot_id"),
        ):
            graph.run(f"MATCH (n:{label}) WHERE n.{key} CONTAINS $token DETACH DELETE n", token=token)
        graph.close()
