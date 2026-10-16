"""Does the golden set have the minimum mix of spec 09 §2? A warning, never a blocker."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from mentormind.core.schemas.evaluation import GoldenQuestion

#: Minimum mix of spec 09 §2 (30 questions in total).
MIN_TOTAL = 30
MIN_PER_TYPE = {"how": 10, "why": 6, "exception": 5, "relational": 5, "out_of_scope": 4}


def check_distribution(questions: Sequence[GoldenQuestion]) -> list[str]:
    """What the set still lacks against spec 09 §2; empty = the minimum mix is met."""
    counts: Counter[str] = Counter(q.type for q in questions)
    missing = []
    if len(questions) < MIN_TOTAL:
        missing.append(f"cần tối thiểu {MIN_TOTAL} câu, đang có {len(questions)}")
    missing += [
        f"{kind}: cần {need}, đang có {counts[kind]}" for kind, need in MIN_PER_TYPE.items() if counts[kind] < need
    ]
    return missing
