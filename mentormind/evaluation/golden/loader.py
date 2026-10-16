"""Load and validate ``data/golden_set/qa.jsonl`` (spec 09 §2, T09-1).

Every line is checked before anything runs; a bad file raises :class:`GoldenSetError` listing each
bad line with its number and field (AC-01), so Đạt can fix them all in one pass.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from mentormind.core.schemas.evaluation import GoldenQuestion


class LineError(BaseModel):
    line: int
    message: str


class GoldenSetError(ValueError):
    def __init__(self, path: Path, errors: list[LineError]) -> None:
        lines = "; ".join(f"dòng {e.line}: {e.message}" for e in errors)
        super().__init__(f"Golden set {path} sai schema, không chạy: {lines}")
        self.errors = errors


def load_golden(path: Path) -> list[GoldenQuestion]:
    """All questions of ``path``; raises :class:`GoldenSetError` on any bad line."""
    questions: list[GoldenQuestion] = []
    errors: list[LineError] = []
    seen: dict[str, int] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            question = GoldenQuestion.model_validate(json.loads(raw))
        except json.JSONDecodeError as exc:
            errors.append(LineError(line=number, message=f"không phải JSON ({exc.msg})"))
            continue
        except ValidationError as exc:
            errors.append(LineError(line=number, message=_describe(exc)))
            continue
        if question.qid in seen:
            errors.append(LineError(line=number, message=f"qid {question.qid} trùng dòng {seen[question.qid]}"))
            continue
        seen[question.qid] = number
        questions.append(question)
    if errors:
        raise GoldenSetError(path, errors)
    return questions


def _describe(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"]) or "(dòng)"
        parts.append(f"{field}: {'thiếu' if error['type'] == 'missing' else error['msg']}")
    return ", ".join(parts)
