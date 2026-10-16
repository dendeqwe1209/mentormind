"""Hybrid vector/graph retrieval with parameterized relational templates."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.llm.context import strictest
from mentormind.core.schemas.common import Citation, DataClassification
from mentormind.knowledge_base.kg.loader import Graph
from mentormind.knowledge_base.store.vector_store import VectorStore

log = logging.getLogger(__name__)

#: Spec 05 §4 step 4: score added to every node the graph touched.
GRAPH_BONUS = 0.1

Template = Literal[
    "steps_of_process",
    "steps_using_part",
    "where_symptom_occurred",
    "root_causes_of_symptom",
    "prevention_steps",
    "lots_with_defect",
]


class Route(BaseModel):
    template: Template | None = None
    process_id: str | None = None
    part_number: str | None = None
    symptom_text: str | None = None
    defect_code: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class RetrievedContext(BaseModel):
    query: str
    process_id: str | None
    passages: list[str]
    graph_facts: list[str]
    citations: list[Citation]
    classifications: list[DataClassification]


TEMPLATES: dict[str, str] = {
    "steps_of_process": (
        "MATCH (p:Process {process_id: $process_id})-[:HAS_STEP]->(s:Step) "
        "RETURN 'Bước ' + toString(s.step_order) + ': ' + s.step AS fact, "
        "'work_profile' AS source_type, s.profile_id AS ref_id, "
        "s.data_classification AS data_classification ORDER BY s.step_order"
    ),
    "steps_using_part": (
        "MATCH (proc:Process)-[:HAS_STEP]->(s:Step)-[:USES_PART]->"
        "(p:Part {part_number: $part_number}) "
        "WHERE $process_id IS NULL OR proc.process_id = $process_id "
        "RETURN 'Bước ' + s.step + ' dùng linh kiện ' + p.part_number AS fact, "
        "'work_profile' AS source_type, s.profile_id AS ref_id, "
        "s.data_classification AS data_classification"
    ),
    # Sigma facts return the labels of every node/edge they are built from (spec 05 AC-11).
    "where_symptom_occurred": (
        "MATCH (l:Lot)-[d:HAS_DEFECT]->(s:Symptom {symptom_id: $symptom_id}) "
        "MATCH (l)-[:PROCESSED_AT]->(p:Process) "
        "WHERE $process_id IS NULL OR p.process_id = $process_id "
        "RETURN 'Lô ' + l.lot_id + ' tại ' + p.process_id + ' có lỗi ' + s.name AS fact, "
        "'sigma' AS source_type, l.lot_id AS ref_id, "
        "[l.data_classification, d.data_classification, s.data_classification] AS data_classification"
    ),
    "root_causes_of_symptom": (
        "MATCH (s:Symptom {symptom_id: $symptom_id})-[:CAUSED_BY]->(c:RootCause) "
        "WHERE $process_id IS NULL OR EXISTS { MATCH (s)-[:DETECTED_AT]->"
        "(:Process {process_id: $process_id}) } "
        "RETURN 'Nguyên nhân của ' + s.name + ': ' + c.description AS fact, "
        "'sigma' AS source_type, 'defect_catalog.csv#' + s.symptom_id AS ref_id, "
        "[s.data_classification, c.data_classification] AS data_classification"
    ),
    "prevention_steps": (
        "MATCH (s:Symptom {symptom_id: $symptom_id})-[:CAUSED_BY]->(c:RootCause)"
        "-[:PREVENTED_BY]->(step:Step) "
        "MATCH (p:Process)-[:HAS_STEP]->(step) "
        "WHERE $process_id IS NULL OR p.process_id = $process_id "
        "RETURN 'Bước phòng ngừa: ' + step.step AS fact, "
        "'work_profile' AS source_type, step.profile_id AS ref_id, "
        "[step.data_classification, s.data_classification, c.data_classification] AS data_classification"
    ),
    "lots_with_defect": (
        "MATCH (l:Lot)-[r:HAS_DEFECT]->(s:Symptom {symptom_id: $symptom_id}) "
        "MATCH (l)-[:PROCESSED_AT]->(p:Process) "
        "WHERE ($date_from IS NULL OR r.date >= $date_from) "
        "AND ($date_to IS NULL OR r.date <= $date_to) "
        "AND ($process_id IS NULL OR p.process_id = $process_id) "
        "RETURN 'Lô ' + l.lot_id + ' có lỗi ' + s.name AS fact, "
        "'sigma' AS source_type, l.lot_id AS ref_id, "
        "[l.data_classification, r.data_classification, s.data_classification] AS data_classification"
    ),
}

PROFILE_EXPANSIONS = (
    "MATCH (s:Step {profile_id: $profile_id})-[:NEXT]-(n:Step) "
    "RETURN 'Bước liên quan: ' + n.step AS fact, 'work_profile' AS source_type, "
    "n.profile_id AS ref_id, n.data_classification AS data_classification",
    "MATCH (s:Step {profile_id: $profile_id})-[:HAS_EXCEPTION]->(e:Exception) "
    "RETURN 'Ngoại lệ ' + e.case + ': ' + e.handling AS fact, "
    "'work_profile' AS source_type, s.profile_id AS ref_id, "
    "s.data_classification AS data_classification",
    "MATCH (s:Step {profile_id: $profile_id})-[:USES_PART]->(p:Part) "
    "RETURN 'Bước ' + s.step + ' dùng linh kiện ' + p.part_number AS fact, "
    "'work_profile' AS source_type, s.profile_id AS ref_id, "
    "s.data_classification AS data_classification",
    "MATCH (s:Step {profile_id: $profile_id})-[:ON_EQUIPMENT]->(e:Equipment) "
    "RETURN 'Bước ' + s.step + ' trên thiết bị ' + e.equipment_id AS fact, "
    "'work_profile' AS source_type, s.profile_id AS ref_id, "
    "s.data_classification AS data_classification",
    "MATCH (e:Expert)-[:CONTRIBUTED]->(s:Step {profile_id: $profile_id}) "
    "RETURN 'Chuyên gia ' + coalesce(e.display_name, e.expert_id) + ' đóng góp bước ' + s.step "
    "AS fact, 'work_profile' AS source_type, s.profile_id AS ref_id, "
    "s.data_classification AS data_classification",
    "MATCH (s:Step {profile_id: $profile_id})-[r:EVIDENCED_BY]->(v:VideoSegment) "
    "RETURN 'Video ' + coalesce(v.video_id, '') + ' đoạn ' + v.segment_id AS fact, "
    "'video_segment' AS source_type, v.segment_id AS ref_id, "
    "s.data_classification AS data_classification, "
    "r.profile_t_start AS t_start, r.profile_t_end AS t_end",
)


def normalize(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if not unicodedata.combining(c))


def token_cost(text: str) -> int:
    """Conservative token estimate for the context budget: two per word or symbol."""
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)) * 2)


# Characters Lucene's classic query parser treats as syntax (QueryParserBase.escape).
_LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/&|])')


def lucene_query(text: str) -> str:
    """Plain text as a Lucene query: lower case (so no AND/OR/NOT operators), syntax escaped."""
    return _LUCENE_SPECIAL.sub(r"\\\1", text.lower())


def _label(value: Any) -> DataClassification:
    """Strictest label among a graph row's parts; a missing label is factory data (fail closed)."""
    labels = value if isinstance(value, list) else [value]
    return strictest(DataClassification(label or DataClassification.FACTORY_CONFIDENTIAL) for label in labels or [None])


@dataclass
class _Candidate:
    """One passage competing for the context budget."""

    text: str
    source_type: str
    ref_id: str
    score: float
    classification: DataClassification
    is_fact: bool
    t_start: float | None = None
    t_end: float | None = None


def _score(a: str, b: str) -> float:
    try:
        from rapidfuzz.fuzz import token_set_ratio
    except ImportError:
        from difflib import SequenceMatcher

        return 100 * SequenceMatcher(None, a, b).ratio()
    return float(token_set_ratio(a, b))


class HybridRetriever:
    def __init__(self, vectors: VectorStore, graph: Graph, *, router: Any = None, token_budget: int = 3000):
        self.vectors = vectors
        self.graph = graph
        self.router = router
        self.token_budget = token_budget

    def close(self) -> None:
        close = getattr(self.graph, "close", None)
        if close is not None:
            close()

    def match_symptom(self, text: str) -> str | None:
        catalog = self.graph.run("MATCH (s:Symptom) RETURN s.symptom_id AS symptom_id, s.name AS name")
        if not catalog or not text.strip():
            return None
        ranked = sorted(
            ((_score(normalize(text), normalize(row["name"])), row["symptom_id"]) for row in catalog),
            reverse=True,
        )
        if ranked[0][0] >= 70:
            return ranked[0][1]
        rows = self.graph.run(
            "CALL db.index.fulltext.queryNodes('symptom_name', $text) YIELD node, score "
            "RETURN node.symptom_id AS symptom_id ORDER BY score DESC LIMIT 1",
            text=lucene_query(text),
        )
        return rows[0]["symptom_id"] if rows else None

    def _route(self, query: str, process_id: str | None) -> Route:
        if self.router is None:
            return Route()
        if getattr(self.router, "is_cloud", False):
            return Route()
        try:
            response = self.router.generate_json(
                "Choose at most one graph template for this question. Return JSON with template "
                "and any needed process_id, part_number, symptom_text, defect_code, date_from, "
                "date_to. Templates: " + ", ".join(TEMPLATES) + "\nQuestion: " + query,
                Route.model_json_schema(),
                classification="factory_confidential",
            )
            route = Route.model_validate(response)
            if process_id is not None:
                route.process_id = process_id
            return route
        except (ProviderError, ValidationError, ValueError, TypeError, KeyError) as exc:
            # Spec 05 §4: a router that fails or answers badly only skips the relational step.
            log.warning("Graph router skipped (%s); using vector + expansion only", type(exc).__name__)
            return Route()

    def run_template(self, template: Template, **parameters: Any) -> list[dict[str, Any]]:
        if template not in TEMPLATES:
            raise ValueError("Unknown graph template")
        params = dict(parameters)
        params.setdefault("process_id", None)
        if template in {"steps_of_process", "steps_using_part"}:
            required = "process_id" if template == "steps_of_process" else "part_number"
            if not params.get(required):
                return []
        else:
            symptom_id = params.get("symptom_id") or params.get("defect_code")
            if not symptom_id and params.get("symptom_text"):
                symptom_id = self.match_symptom(params["symptom_text"])
            if not symptom_id:
                return []
            params["symptom_id"] = symptom_id
            params.setdefault("date_from", None)
            params.setdefault("date_to", None)
        return self.graph.run(TEMPLATES[template], **params)

    def retrieve(self, query: str, process_id: str | None = None, k: int = 8) -> RetrievedContext:
        filters = {"process_id": process_id} if process_id else None
        hits = self.vectors.search(query, k=k, filters=filters)
        candidates: dict[tuple[str, str, str], _Candidate] = {}
        #: (source_type, ref_id) of every node the graph touched (spec 05 §4 step 4).
        touched: set[tuple[str, str]] = set()
        for hit in hits:
            chunk = hit.chunk
            candidates[(chunk.source_type, chunk.ref_id, chunk.chunk_id)] = _Candidate(
                chunk.text, chunk.source_type, chunk.ref_id, hit.score, chunk.data_classification, is_fact=False
            )
            rows: list[dict[str, Any]] = []
            if chunk.source_type == "work_profile":
                for statement in PROFILE_EXPANSIONS:
                    rows += self.graph.run(statement, profile_id=chunk.ref_id)
            elif chunk.source_type == "document":
                rows = self.graph.run(
                    "MATCH (p:Process)-[:HAS_STEP]->(s:Step)-[:REFERENCES]->"
                    "(d:Document {doc_id: $doc_id}) "
                    "WHERE $process_id IS NULL OR p.process_id = $process_id "
                    "RETURN s.step AS fact, 'work_profile' AS source_type, s.profile_id AS ref_id, "
                    "s.data_classification AS data_classification",
                    doc_id=chunk.ref_id,
                    process_id=process_id,
                )
            if rows:
                touched.add((chunk.source_type, chunk.ref_id))
            # A hit's facts get its score with the bonus, which the hit itself gets below: they tie
            # and the stable sort keeps them right after it, never above it.
            self._add_rows(candidates, touched, rows, hit.score + GRAPH_BONUS)
        route = self._route(query, process_id)
        if route.template:
            rows = self.run_template(route.template, **route.model_dump(exclude={"template"}))
            self._add_rows(candidates, touched, rows, GRAPH_BONUS)
        for candidate in candidates.values():
            if not candidate.is_fact and (candidate.source_type, candidate.ref_id) in touched:
                candidate.score += GRAPH_BONUS
        passages, facts, citations, classifications = [], [], [], []
        budget = self.token_budget
        for candidate in sorted(candidates.values(), key=lambda c: -c.score):
            cost = token_cost(candidate.text)
            if cost > budget:
                continue
            passages.append(candidate.text)
            citations.append(
                Citation(
                    source_type=candidate.source_type,
                    ref_id=candidate.ref_id,
                    snippet=candidate.text,
                    score=candidate.score,
                    t_start=candidate.t_start,
                    t_end=candidate.t_end,
                )
            )
            classifications.append(candidate.classification)
            if candidate.is_fact:
                facts.append(candidate.text)
            budget -= cost
        return RetrievedContext(
            query=query,
            process_id=process_id,
            passages=passages,
            graph_facts=facts,
            citations=citations,
            classifications=classifications,
        )

    @staticmethod
    def _add_rows(
        candidates: dict[tuple[str, str, str], _Candidate],
        touched: set[tuple[str, str]],
        rows: list[dict[str, Any]],
        score: float,
    ) -> None:
        for row in rows:
            fact, ref_id = row.get("fact"), row.get("ref_id")
            if not fact or not ref_id:
                continue
            source_type = row.get("source_type", "work_profile")
            touched.add((source_type, ref_id))
            key = (source_type, ref_id, fact)
            if key in candidates and candidates[key].score >= score:
                continue  # duplicate fact: keep the highest score (and its first position)
            candidates[key] = _Candidate(
                fact,
                source_type,
                ref_id,
                score,
                _label(row.get("data_classification")),
                is_fact=True,
                t_start=row.get("t_start"),
                t_end=row.get("t_end"),
            )


def get_hybrid_retriever(settings: Any = None) -> HybridRetriever:
    """Build the configured store, graph and guarded LLM router for application use."""
    from mentormind.core.config import get_settings
    from mentormind.core.providers.errors import ProviderConfigError
    from mentormind.core.providers.llm.factory import get_llm_provider
    from mentormind.knowledge_base.kg.client import Neo4jGraph
    from mentormind.knowledge_base.store.vector_store import get_vector_store

    settings = settings or get_settings()
    vectors = get_vector_store(settings)
    try:
        router = get_llm_provider(settings)
    except ProviderConfigError:
        router = None
    return HybridRetriever(vectors, Neo4jGraph(settings), router=router)
