"""Pass A answers must be in Vietnamese (spec 04 §3): the user reads them as SOP steps.

The Q4 Qwen3-VL on Ollama thinks in English and often answers in English too (LASI sweep
2026-10-04: 63-83% of the step names). Vietnamese prose almost always carries diacritics, so a text
of two or more words with none of them is taken as English. Short tokens (codes, "SCARA", "OK")
are not judged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from mentormind.processing.vlm.passes.models import PassAOutput

_VIETNAMESE = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z]{2,}")


def looks_english(text: str | None) -> bool:
    """True for a text of 2+ Latin words without a single Vietnamese letter."""
    if not text:
        return False
    return len(_WORD.findall(text)) >= 2 and not _VIETNAMESE.search(text)


def english_fields(output: PassAOutput) -> list[str]:
    """``steps[i].field`` of every step text that looks English (empty: all Vietnamese)."""
    found = []
    for i, step in enumerate(output.steps):
        texts: Iterable[tuple[str, str | None]] = (
            ("step", step.step),
            ("hand_action", step.hand_action),
            ("key_point_observed", step.key_point_observed),
        )
        found += [f"steps[{i}].{name}" for name, text in texts if looks_english(text)]
    return found
