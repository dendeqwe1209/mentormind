"""Publish reviewed profiles and Sigma records to the graph and vector index."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Protocol

from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.vector import VectorChunk
from mentormind.knowledge_base.store.vector_store import VectorStore

log = logging.getLogger(__name__)


class Graph(Protocol):
    def run(self, query: str, **params: Any) -> list[dict[str, Any]]: ...


@dataclass
class LoadResult:
    loaded: int = 0
    skipped: int = 0
    stale: int = 0


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _text(profile: Any) -> str:
    fields = [profile.step, profile.hand_action, profile.key_point, profile.reason]
    fields.extend(f"{item.case}: {item.handling}" for item in profile.exceptions)
    return "\n".join(str(field) for field in fields if field)


class KnowledgeGraphLoader:
    def __init__(self, graph: Graph, vectors: VectorStore):
        self.graph = graph
        self.vectors = vectors

    def load_profiles(self, profiles: Any) -> LoadResult:
        result = LoadResult()
        for profile in profiles:
            if _value(profile.status) != "approved":
                result.skipped += 1
                continue
            prior = self.graph.run(
                "MATCH (s:Step {profile_id: $profile_id}) "
                "OPTIONAL MATCH (p:Process)-[:HAS_STEP]->(s) "
                "RETURN s.version AS version, p.process_id AS process_id",
                profile_id=profile.profile_id,
            )
            if prior and prior[0]["version"] > profile.version:
                result.stale += 1
                continue
            touched = {profile.process_id}
            if prior and prior[0].get("process_id"):
                touched.add(prior[0]["process_id"])
            old = self.vectors.search("", k=1, filters={"source_type": "work_profile", "ref_id": profile.profile_id})
            transaction = getattr(self.graph, "transaction", None)
            try:
                with transaction() if transaction is not None else nullcontext():
                    self._load_one(profile)
                    for process_id in touched:
                        self._rebuild_next(process_id)
            except Exception:
                try:
                    if old:
                        self.vectors.upsert([old[0].chunk])
                    else:
                        self.vectors.delete([profile.profile_id])
                except Exception:
                    log.exception("Could not restore vector chunk for %s", profile.profile_id)
                raise
            result.loaded += 1
        return result

    def _load_one(self, p: Any) -> None:
        pid = p.profile_id
        self.graph.run(
            "MATCH (old:Process)-[r:HAS_STEP]->(s:Step {profile_id: $profile_id}) "
            "WHERE old.process_id <> $process_id DELETE r",
            profile_id=pid,
            process_id=p.process_id,
        )
        self.graph.run(
            "MERGE (p:Process {process_id: $process_id}) "
            "MERGE (s:Step {profile_id: $profile_id}) "
            "SET s += $properties "
            "MERGE (p)-[r:HAS_STEP]->(s) SET r.order = $step_order",
            process_id=p.process_id,
            profile_id=pid,
            step_order=p.step_order,
            properties={
                "step": p.step,
                "step_order": p.step_order,
                "hand_action": p.hand_action,
                "key_point": p.key_point,
                "reason": p.reason,
                "reason_source": _value(p.reason_source) if p.reason_source else None,
                "pass_criteria": p.pass_criteria,
                "confidence": p.confidence,
                "version": p.version,
                "reviewer": p.review.reviewer,
                "data_classification": _value(p.data_classification),
            },
        )
        # Rebuild all relationships owned by this Step; shared target nodes remain intact.
        self.graph.run(
            "MATCH (s:Step {profile_id: $profile_id})-[r:HAS_EXCEPTION|USES_PART|ON_EQUIPMENT|"
            "EVIDENCED_BY|REFERENCES]->() DELETE r",
            profile_id=pid,
        )
        self.graph.run(
            "MATCH (:Expert)-[r:CONTRIBUTED]->(s:Step {profile_id: $profile_id}) DELETE r",
            profile_id=pid,
        )
        self.graph.run(
            "MATCH (s:Step {profile_id: $profile_id}) "
            "UNWIND $exceptions AS item "
            "MERGE (e:Exception {exception_id: item.id}) SET e.case = item.case, e.handling = item.handling "
            "MERGE (s)-[:HAS_EXCEPTION]->(e)",
            profile_id=pid,
            exceptions=[
                {"id": f"{pid}#{i}", "case": x.case, "handling": x.handling} for i, x in enumerate(p.exceptions)
            ],
        )
        self.graph.run(
            "MATCH (e:Exception) WHERE e.exception_id STARTS WITH $prefix "
            "AND NOT EXISTS { MATCH ()-[:HAS_EXCEPTION]->(e) } DELETE e",
            prefix=pid + "#",
        )
        self.graph.run(
            "MATCH (s:Step {profile_id: $profile_id}) UNWIND $parts AS part_number "
            "MERGE (p:Part {part_number: part_number}) MERGE (s)-[:USES_PART]->(p)",
            profile_id=pid,
            parts=sorted(set(p.part_numbers)),
        )
        if p.equipment_id:
            self.graph.run(
                "MATCH (s:Step {profile_id: $profile_id}) "
                "MERGE (e:Equipment {equipment_id: $equipment_id}) MERGE (s)-[:ON_EQUIPMENT]->(e)",
                profile_id=pid,
                equipment_id=p.equipment_id,
            )
        if p.expert and p.expert.expert_id:
            self.graph.run(
                "MATCH (s:Step {profile_id: $profile_id}) "
                "MERGE (e:Expert {expert_id: $expert_id}) SET e.display_name = $display_name "
                "MERGE (e)-[:CONTRIBUTED]->(s)",
                profile_id=pid,
                expert_id=p.expert.expert_id,
                display_name=p.expert.display_name,
            )
        self.graph.run(
            "MATCH (s:Step {profile_id: $profile_id}) UNWIND $segment_ids AS segment_id "
            "MERGE (v:VideoSegment {segment_id: segment_id}) "
            "SET v.video_id = $video_id "
            "MERGE (s)-[r:EVIDENCED_BY]->(v) "
            "SET r.profile_t_start = $t_start, r.profile_t_end = $t_end",
            profile_id=pid,
            segment_ids=sorted(set(p.evidence.segment_ids)),
            video_id=p.evidence.video_id,
            t_start=p.evidence.t_start,
            t_end=p.evidence.t_end,
        )
        self.graph.run(
            "MATCH (s:Step {profile_id: $profile_id}) UNWIND $doc_ids AS doc_id "
            "MERGE (d:Document {doc_id: doc_id}) MERGE (s)-[:REFERENCES]->(d)",
            profile_id=pid,
            doc_ids=sorted(set(p.evidence.document_refs)),
        )
        self.graph.run(
            "MATCH (c:RootCause {prevention_profile_id: $profile_id}), "
            "(s:Step {profile_id: $profile_id}) MERGE (c)-[:PREVENTED_BY]->(s)",
            profile_id=pid,
        )
        self.vectors.upsert(
            [
                VectorChunk(
                    chunk_id=pid,
                    source_type="work_profile",
                    ref_id=pid,
                    text=_text(p),
                    process_ids=[p.process_id],
                    part_numbers=p.part_numbers,
                    data_classification=_value(p.data_classification),
                    metadata={"version": p.version, "reviewer": p.review.reviewer},
                )
            ]
        )

    def _rebuild_next(self, process_id: str) -> None:
        self.graph.run(
            "MATCH (:Process {process_id: $process_id})-[:HAS_STEP]->(a:Step)-[r:NEXT]->(:Step) DELETE r",
            process_id=process_id,
        )
        self.graph.run(
            "MATCH (:Process {process_id: $process_id})-[:HAS_STEP]->(s:Step) "
            "WITH s ORDER BY s.step_order, s.profile_id WITH collect(s) AS steps "
            "WITH steps WHERE size(steps) > 1 "
            "UNWIND range(0, size(steps)-2) AS i "
            "WITH steps[i] AS a, steps[i+1] AS b MERGE (a)-[:NEXT]->(b)",
            process_id=process_id,
        )

    def unload_profile(self, profile_id: str) -> None:
        old = self.vectors.search("", k=1, filters={"source_type": "work_profile", "ref_id": profile_id})
        transaction = getattr(self.graph, "transaction", None)
        try:
            with transaction() if transaction is not None else nullcontext():
                rows = self.graph.run(
                    "MATCH (p:Process)-[:HAS_STEP]->(s:Step {profile_id: $profile_id}) "
                    "RETURN p.process_id AS process_id",
                    profile_id=profile_id,
                )
                self.graph.run(
                    "MATCH (s:Step {profile_id: $profile_id}) DETACH DELETE s",
                    profile_id=profile_id,
                )
                self.graph.run(
                    "MATCH (e:Exception) WHERE e.exception_id STARTS WITH $prefix "
                    "AND NOT EXISTS { MATCH ()-[:HAS_EXCEPTION]->(e) } DELETE e",
                    prefix=profile_id + "#",
                )
                for row in rows:
                    self._rebuild_next(row["process_id"])
                self.vectors.delete([profile_id])
        except Exception:
            if old:
                try:
                    self.vectors.upsert([old[0].chunk])
                except Exception:
                    log.exception("Could not restore vector chunk for %s", profile_id)
            raise

    def load_sigma(
        self,
        adapter: Any,
        classification: DataClassification | str = DataClassification.FACTORY_CONFIDENTIAL,
    ) -> int:
        """Load read-only Sigma adapter records; prevention edges need a published Step.

        ``classification`` labels the source (constitution art. 2): it is written on every Lot,
        HAS_DEFECT, Symptom and RootCause so retrieval can keep factory data off the cloud.
        """
        label = DataClassification(classification).value
        transaction = getattr(self.graph, "transaction", None)
        with transaction() if transaction is not None else nullcontext():
            return self._load_sigma(adapter, label)

    def _load_sigma(self, adapter: Any, classification: str) -> int:
        count = 0
        for lot in adapter.list_lots():
            self.graph.run(
                "MATCH (l:Lot {lot_id: $lot_id})-[r:PROCESSED_AT]->(p:Process) "
                "WHERE p.process_id <> $process_id DELETE r",
                lot_id=lot.lot_id,
                process_id=lot.process_id,
            )
            self.graph.run(
                "MERGE (l:Lot {lot_id: $lot_id}) "
                "SET l.product_code = $product_code, l.data_classification = $classification "
                "MERGE (p:Process {process_id: $process_id}) "
                "MERGE (l)-[r:PROCESSED_AT]->(p) "
                "SET r.date = $date, r.shift = $shift, r.operator_id = $operator_id",
                lot_id=lot.lot_id,
                product_code=lot.product_code,
                process_id=lot.process_id,
                date=str(lot.date),
                shift=lot.shift,
                operator_id=lot.operator_id,
                classification=classification,
            )
            count += 1
        for item in adapter.defect_catalog():
            self.graph.run(
                "MATCH (s:Symptom {symptom_id: $symptom_id})-[r:CAUSED_BY]->(c:RootCause) "
                "WHERE $cause_id IS NULL OR c.cause_id <> $cause_id DELETE r",
                symptom_id=item.defect_code,
                cause_id=item.known_root_cause_id,
            )
            if item.known_root_cause_id:
                self.graph.run(
                    "MATCH (c:RootCause {cause_id: $cause_id})-[r:PREVENTED_BY]->(s:Step) "
                    "WHERE $profile_id IS NULL OR s.profile_id <> $profile_id DELETE r",
                    cause_id=item.known_root_cause_id,
                    profile_id=item.prevention_profile_id,
                )
            self.graph.run(
                "MERGE (s:Symptom {symptom_id: $symptom_id}) "
                "SET s.name = $name, s.data_classification = $classification "
                "WITH s WHERE $cause_id IS NOT NULL "
                "MERGE (c:RootCause {cause_id: $cause_id}) "
                "SET c.description = $description, c.prevention_profile_id = $profile_id, "
                "c.data_classification = $classification "
                "MERGE (s)-[r:CAUSED_BY]->(c) SET r.source = 'sigma_catalog' "
                "WITH c WHERE $profile_id IS NOT NULL "
                "MATCH (step:Step {profile_id: $profile_id}) MERGE (c)-[:PREVENTED_BY]->(step)",
                symptom_id=item.defect_code,
                name=item.symptom_name,
                cause_id=item.known_root_cause_id,
                description=item.known_root_cause,
                profile_id=item.prevention_profile_id,
                classification=classification,
            )
        touched_symptoms: set[str] = set()
        for defect in adapter.list_defects():
            old = self.graph.run(
                "MATCH (:Lot)-[r:HAS_DEFECT {defect_id: $defect_id}]->(s:Symptom) "
                "RETURN DISTINCT s.symptom_id AS symptom_id",
                defect_id=defect.defect_id,
            )
            touched_symptoms.update(row["symptom_id"] for row in old)
            touched_symptoms.add(defect.defect_code)
            self.graph.run(
                "MATCH (l:Lot)-[r:HAS_DEFECT {defect_id: $defect_id}]->(s:Symptom) "
                "WHERE l.lot_id <> $lot_id OR s.symptom_id <> $symptom_id DELETE r",
                lot_id=defect.lot_id,
                symptom_id=defect.defect_code,
                defect_id=defect.defect_id,
            )
            self.graph.run(
                "MATCH (l:Lot {lot_id: $lot_id}), (p:Process {process_id: $process_id}) "
                "MERGE (s:Symptom {symptom_id: $symptom_id}) "
                "ON CREATE SET s.data_classification = $classification "
                "MERGE (l)-[r:HAS_DEFECT {defect_id: $defect_id}]->(s) "
                "SET r.date = $date, r.qty = $qty, r.data_classification = $classification "
                "MERGE (s)-[:DETECTED_AT]->(p)",
                lot_id=defect.lot_id,
                process_id=defect.process_id,
                symptom_id=defect.defect_code,
                defect_id=defect.defect_id,
                date=str(defect.detected_at.date()),
                qty=defect.qty,
                classification=classification,
            )
        for symptom_id in touched_symptoms:
            self.graph.run(
                "MATCH (s:Symptom {symptom_id: $symptom_id})-[r:DETECTED_AT]->(:Process) DELETE r",
                symptom_id=symptom_id,
            )
            self.graph.run(
                "MATCH (s:Symptom {symptom_id: $symptom_id})<-[:HAS_DEFECT]-(l:Lot)"
                "-[:PROCESSED_AT]->(p:Process) MERGE (s)-[:DETECTED_AT]->(p)",
                symptom_id=symptom_id,
            )
        return count

    def stats(self) -> dict[str, int]:
        return {
            label: self.graph.run(f"MATCH (n:{label}) RETURN count(n) AS count")[0]["count"]
            for label in ("Process", "Step", "Symptom", "Lot")
        }
