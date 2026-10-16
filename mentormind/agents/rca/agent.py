"""RCA Agent (spec 06 §4, T06-3): a lot or a symptom in, cause hypotheses and a 5-Why draft out.

1. A lot -> Sigma ``get_lot`` + ``get_defects`` (``LotNotFound`` goes through); the lot's
   ``defect_code`` IS the ``symptom_id`` (deterministic). A symptom text -> spec 05's matcher.
2. Graph templates called BY NAME (``root_causes_of_symptom``, ``where_symptom_occurred``,
   ``prevention_steps``); the LLM router of spec 05 is never involved (AC-08): the factory hands
   in a ``HybridRetriever`` built without a router.
3. The retriever adds related steps and exceptions.
4. The LLM writes the report as JSON over numbered evidence (``prompts/rca.md``); the code then
   decides what the evidence supports: a hypothesis without evidence is ``low``, a why-level
   without evidence is ``verified=False``, 3..5 levels, at most 3 hypotheses sorted by likelihood.
   An unreadable answer (twice) falls back to the graph's own root causes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mentormind.agents.base import Agent, AgentRun, PromptBook, TraceLog, row_label
from mentormind.agents.ports import GraphTemplates, Retriever, SigmaSource
from mentormind.agents.rca.report import DISCLAIMER, RCA_SCHEMA, LlmReport, five_why, hypotheses
from mentormind.core.providers.errors import InvalidJSONError
from mentormind.core.providers.llm import LLMProvider, strictest
from mentormind.core.providers.parsing import parse_json_object
from mentormind.core.schemas import Citation, DataClassification
from mentormind.core.schemas.agents import RcaReport, RcaRequest
from mentormind.knowledge_base.retrieval.hybrid import RetrievedContext, Template
from mentormind.knowledge_base.sigma.adapter import DefectRecord, LotRecord

TEMPLATES: tuple[Template, ...] = (
    "root_causes_of_symptom",
    "where_symptom_occurred",
    "prevention_steps",
)


class RcaAgent(Agent[RcaRequest, RcaReport]):
    kind = "rca"
    prompts = PromptBook(Path(__file__).resolve().parent / "prompts")

    def __init__(
        self,
        llm: LLMProvider,
        graph: GraphTemplates,
        retriever: Retriever,
        sigma: SigmaSource | None = None,
        *,
        sigma_classification: DataClassification = DataClassification.FACTORY_CONFIDENTIAL,
        trace: TraceLog | None = None,
    ) -> None:
        super().__init__(llm, trace=trace)
        self.graph = graph
        self.retriever = retriever
        self.sigma = sigma
        #: Label of Sigma and graph facts; real Sigma data is factory data (fail closed).
        self.sigma_classification = sigma_classification

    def investigate(self, request: RcaRequest) -> RcaReport:
        """Hypotheses + 5-Why for a lot or a symptom (spec 06 FR-02). Raises ``LotNotFound``."""
        return self.run(request)

    def _run(self, request: RcaRequest, call: AgentRun) -> RcaReport:
        lot, defects, symptom, process_id, symptom_ids = self._symptoms(request)
        rows: dict[str, list[dict[str, Any]]] = {
            name: [row for sid in symptom_ids for row in self.graph.run_template(name, symptom_id=sid)]
            for name in TEMPLATES
        }
        query = f"Lỗi {symptom} ở công đoạn {process_id or ''}: bước thao tác, ngoại lệ, phòng ngừa"
        context = self.retriever.retrieve(query, process_id)
        evidence, causes, labels = self._evidence(defects, lot, rows, context)
        call.context_ids = [c.ref_id for c in evidence]
        prompt = self.prompts.render(
            "rca.md",
            symptom=symptom,
            process_id=process_id or "(chưa rõ)",
            lot_line=_lot_line(lot),
            evidence="\n".join(f"[{i}] ({c.ref_id}) {c.snippet}" for i, c in enumerate(evidence, 1)),
        )
        parsed = self._ask(prompt, strictest(labels), call)
        return RcaReport(
            lot_id=lot.lot_id if lot else None,
            symptom=symptom,
            hypotheses=hypotheses(parsed, evidence, causes),
            five_why=five_why(parsed, evidence, symptom),
            related_lots=sorted(
                {r["ref_id"] for r in rows["where_symptom_occurred"] if r.get("ref_id")}
                - ({lot.lot_id} if lot else set())
            ),
            prevention_steps=list(dict.fromkeys(r["ref_id"] for r in rows["prevention_steps"] if r.get("ref_id"))),
            disclaimer=DISCLAIMER,
        )

    def _symptoms(self, request: RcaRequest) -> tuple[LotRecord | None, list[DefectRecord], str, str | None, list[str]]:
        if request.lot_id:
            if self.sigma is None:
                raise ValueError("RCA theo lot cần Sigma adapter (spec 07).")
            lot = self.sigma.get_lot(request.lot_id)
            defects = self.sigma.get_defects(request.lot_id)
            codes = list(dict.fromkeys(d.defect_code for d in defects))
            symptom = "; ".join(dict.fromkeys(d.description for d in defects)) or "không ghi nhận lỗi"
            return lot, defects, symptom, lot.process_id, codes
        text = request.symptom_text or ""
        matched = self.graph.match_symptom(text)
        return None, [], text, request.process_id, [matched] if matched else []

    def _evidence(
        self,
        defects: list[DefectRecord],
        lot: LotRecord | None,
        rows: dict[str, list[dict[str, Any]]],
        context: RetrievedContext,
    ) -> tuple[list[Citation], list[Citation], list[DataClassification]]:
        """Numbered evidence for the prompt, the known root causes among it, and their labels."""
        evidence = [Citation(source_type="sigma", ref_id=d.defect_id, snippet=_defect_line(d, lot)) for d in defects]
        labels = [self.sigma_classification] * len(evidence)
        causes: list[Citation] = []
        for name, source_type in (
            ("root_causes_of_symptom", "sigma"),
            ("prevention_steps", "work_profile"),
        ):
            for row in rows[name]:
                if not (row.get("ref_id") and row.get("fact")):
                    continue
                citation = Citation(source_type=source_type, ref_id=row["ref_id"], snippet=row["fact"])
                evidence.append(citation)
                labels.append(row_label(row))
                if name == "root_causes_of_symptom":
                    causes.append(citation)
        for passage, _ in self.allowed_passages(context):
            evidence.append(Citation(source_type="work_profile", ref_id=passage.ref_id, snippet=passage.text))
            labels.append(passage.classification)
        return evidence, causes, labels or [self.sigma_classification]

    def _ask(self, prompt: str, label: DataClassification, call: AgentRun) -> LlmReport | None:
        for attempt in range(2):
            text_prompt = prompt if attempt == 0 else prompt + "\n\nLƯU Ý: chỉ trả về JSON hợp lệ."
            response = self.generate(call, text_prompt, classification=label, json_schema=RCA_SCHEMA, temperature=0.2)
            try:
                return LlmReport.model_validate(parse_json_object(response.text))
            except (InvalidJSONError, ValidationError):
                continue
        return None


def _lot_line(lot: LotRecord | None) -> str:
    if lot is None:
        return ""
    return (
        f"Lot {lot.lot_id}: sản phẩm {lot.product_code}, ngày {lot.date}, ca {lot.shift}, "
        f"người vận hành {lot.operator_id}, {lot.qty} cái."
    )


def _defect_line(defect: DefectRecord, lot: LotRecord | None) -> str:
    where = f"{lot.date}, ca {lot.shift}, người vận hành {lot.operator_id}" if lot else "?"
    return f"Lot {defect.lot_id} ({where}): {defect.defect_code} {defect.description}, {defect.qty} cái"
