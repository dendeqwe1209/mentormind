"""The RCA report from the LLM's JSON: what the evidence supports, whatever the LLM claims.

A hypothesis without evidence is ``low``; a why-level without evidence is ``verified=False``;
3..5 levels; at most 3 hypotheses, most likely first. No usable answer -> the graph's own
root causes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mentormind.core.schemas import Citation
from mentormind.core.schemas.agents import Hypothesis, Likelihood, WhyStep

DISCLAIMER = (
    "Đây là giả thuyết dựa trên dữ liệu hiện có, chưa phải kết luận: cần xác minh tại hiện trường trước khi xử lý."
)
UNVERIFIED = "Chưa có căn cứ, cần xác minh tại hiện trường."
MIN_WHY, MAX_WHY, MAX_HYPOTHESES = 3, 5, 3
_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

RCA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cause": {"type": "string"},
                    "likelihood": {"enum": ["high", "medium", "low"]},
                    "evidence_ids": {"type": "array", "items": {"type": "integer"}},
                    "check_actions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["cause", "likelihood", "evidence_ids"],
            },
        },
        "five_why": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "why": {"type": "string"},
                    "answer": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["why", "answer", "evidence_ids"],
            },
        },
    },
    "required": ["hypotheses", "five_why"],
}


class LlmHypothesis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cause: str = Field(min_length=1)
    likelihood: Likelihood
    evidence_ids: list[int] = Field(default_factory=list)
    check_actions: list[str] = Field(default_factory=list)


class LlmWhy(BaseModel):
    model_config = ConfigDict(extra="ignore")
    why: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    evidence_ids: list[int] = Field(default_factory=list)


class LlmReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hypotheses: list[LlmHypothesis] = Field(default_factory=list)
    five_why: list[LlmWhy] = Field(default_factory=list)


def cited_evidence(ids: list[int], evidence: list[Citation]) -> list[Citation]:
    return [evidence[i - 1] for i in dict.fromkeys(ids) if 1 <= i <= len(evidence)]


def hypotheses(parsed: LlmReport | None, evidence: list[Citation], causes: list[Citation]) -> list[Hypothesis]:
    if parsed is None or not parsed.hypotheses:
        # No usable answer: the graph's known root causes are the hypotheses.
        return [
            Hypothesis(cause=cause.snippet.split(": ", 1)[-1], likelihood="medium", evidence=[cause])
            for cause in causes[:MAX_HYPOTHESES]
        ]
    result = []
    for h in parsed.hypotheses:
        cited = cited_evidence(h.evidence_ids, evidence)
        likelihood: Likelihood = h.likelihood if cited else "low"
        result.append(Hypothesis(cause=h.cause, likelihood=likelihood, evidence=cited, check_actions=h.check_actions))
    result.sort(key=lambda h: _RANK[h.likelihood])
    return result[:MAX_HYPOTHESES]


def five_why(parsed: LlmReport | None, evidence: list[Citation], symptom: str) -> list[WhyStep]:
    steps = [
        WhyStep(why=w.why, answer=w.answer, verified=bool(cited_evidence(w.evidence_ids, evidence)))
        for w in (parsed.five_why if parsed else [])
    ][:MAX_WHY]
    while len(steps) < MIN_WHY:
        level = len(steps) + 1
        why = f"Vì sao xảy ra lỗi {symptom}?" if level == 1 else f"Vì sao (tầng {level})?"
        steps.append(WhyStep(why=why, answer=UNVERIFIED, verified=False))
    return steps
