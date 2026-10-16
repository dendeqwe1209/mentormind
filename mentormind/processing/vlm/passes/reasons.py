"""``propose-reasons`` — a reason only from the expert's own words (spec 04 §5, T04-7, T04-18).

For each draft whose evidence carries a ``transcript_excerpt`` (what the expert said during
that step), a text LLM answers ``{"has_reason": bool, "purpose_span": str|null}``: whether the
expert says why / for what purpose, and the short part of the words that says it, copied verbatim.
The answer is checked, never trusted:

- an excerpt with fewer than ``MIN_EXCERPT_LETTERS`` letters is junk (a stray ASR word such as
  "falling"): the LLM is not even asked;
- the span must be in the excerpt: ``rapidfuzz.fuzz.partial_ratio >= QUOTE_THRESHOLD`` on
  lowercased text, below that the LLM paraphrased or invented. A span longer than the excerpt is
  scored with ``fuzz.ratio`` against the whole excerpt: ``partial_ratio`` would look for the excerpt
  inside the span, so "the whole excerpt + an invented purpose" would score 100;
- the span must have at least ``MIN_SPAN_LETTERS`` letters.

"Letters" are Unicode letters (``str.isalpha``): no spaces, digits, punctuation or combining marks,
so the rule holds for Thai, written without spaces between words. What is stored as ``reason`` is
the expert's full sentence(s) of the excerpt holding the span, never the span or any AI wording;
it sets ``reason_source="expert_verbal"`` and moves the profile to ``in_review`` (constitution
art. 3). The sentences are those holding the characters that matched, not the whole alignment
window, which can reach one character into a neighbouring sentence. Every profile examined gets one
line in ``reasons_audit.jsonl`` for the user's self-check; an accepted one only once it is saved.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from rapidfuzz import fuzz
from rapidfuzz.distance import Indel

from mentormind.core.providers.errors import InvalidJSONError
from mentormind.core.providers.llm import LLMProvider
from mentormind.core.providers.parsing import parse_json_object
from mentormind.core.schemas.reason_audit import ReasonAuditRecord, ReasonDecision
from mentormind.core.schemas.work_profile import WorkProfile, validate_against_contract
from mentormind.processing.vlm.passes.prompting import render_prompt

log = logging.getLogger(__name__)
#: One audit line at a time: proposals may run on several threads.
_AUDIT_LOCK = threading.Lock()

#: ``partial_ratio`` (0-100, lowercased) the purpose span must reach against the excerpt.
QUOTE_THRESHOLD = 85.0
#: Fewer letters than this in the purpose span: junk.
MIN_SPAN_LETTERS = 6
#: Fewer letters than this in the whole excerpt: junk, the LLM is not asked.
MIN_EXCERPT_LETTERS = 12
#: The audit file, in ``<work_dir>/vlm/<video_id>/`` next to the describe artefacts (FR-06).
AUDIT_FILE = "reasons_audit.jsonl"

REASON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "has_reason": {"type": "boolean"},
        "purpose_span": {"type": ["string", "null"]},
    },
    "required": ["has_reason", "purpose_span"],
}

#: A sentence ends at . ! ? … (also CJK full-width) followed by whitespace, or at a line break.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…。！？])\s+|\n+")


def reasons_audit_path(work_dir: Path, video_id: str) -> Path:
    """``<work_dir>/vlm/<video_id>/reasons_audit.jsonl``: same place for the CLI and the API."""
    return work_dir / "vlm" / video_id / AUDIT_FILE


def letter_count(text: str) -> int:
    """Unicode letters in ``text``: spaces, digits, punctuation and combining marks do not count."""
    return sum(char.isalpha() for char in text)


def propose_reasons(
    profiles: Sequence[WorkProfile],
    llm: LLMProvider,
    *,
    audit: Path | None = None,
    save: Callable[[WorkProfile], object] | None = None,
) -> list[WorkProfile]:
    """Profiles with a verbatim expert reason filled in; the others unchanged (AC-08, AC-09, AC-25..27).

    Only drafts are examined (excerpt, no reason yet): a step a reviewer already handled is left
    alone. Each one examined appends one line to ``audit`` when given. ``save`` stores an accepted
    profile as soon as it is decided, and its ``accepted`` line is written only after ``save``
    returned: a run that stops half-way (the LLM times out) never leaves a line claiming a reason
    the store does not hold.
    """
    return [_propose(profile, llm, audit, save) for profile in profiles]


def examined(profile: WorkProfile) -> bool:
    """Whether ``propose_reasons`` looks at ``profile``: a draft with an excerpt and no reason."""
    excerpt = profile.evidence.transcript_excerpt if profile.evidence else None
    return profile.status == "draft" and bool(excerpt) and profile.reason is None


def _propose(
    profile: WorkProfile, llm: LLMProvider, audit: Path | None, save: Callable[[WorkProfile], object] | None
) -> WorkProfile:
    excerpt = profile.evidence.transcript_excerpt if profile.evidence else None
    if not excerpt or not examined(profile):
        return profile
    record = ReasonAuditRecord(
        profile_id=profile.profile_id,
        step=profile.step,
        transcript_excerpt=excerpt,
        decision="unreadable",  # every path of _decide sets the real one
        timestamp=datetime.now(UTC),
    )
    updated = _decide(profile, excerpt, llm, record)
    if save is not None and record.decision == "accepted":
        save(updated)
    _write(record, audit)
    return updated


def _decide(profile: WorkProfile, excerpt: str, llm: LLMProvider, record: ReasonAuditRecord) -> WorkProfile:
    """Fill ``record`` with what happened; the profile with its reason, or unchanged."""
    letters = letter_count(excerpt)
    if letters < MIN_EXCERPT_LETTERS:
        record.junk, record.junk_why = True, f"excerpt has {letters} letters (< {MIN_EXCERPT_LETTERS})"
        return _reject(profile, record, "rejected_junk")
    record.model = llm.model
    response = llm.generate(
        _prompt(profile, excerpt),
        classification=profile.data_classification,
        json_schema=REASON_SCHEMA,
        temperature=0.0,
    )
    try:
        answer = parse_json_object(response.text)
    except InvalidJSONError:
        return _reject(profile, record, "unreadable")
    has_reason, span = answer.get("has_reason"), answer.get("purpose_span")
    if not isinstance(has_reason, bool) or not (span is None or isinstance(span, str)):
        return _reject(profile, record, "unreadable")
    record.has_reason, record.purpose_span = has_reason, span
    if not has_reason or span is None or not span.strip():
        return _reject(profile, record, "no_reason")
    span = span.strip()
    score, start, end = locate(span, excerpt)
    record.match_score = round(score, 1)
    span_letters = letter_count(span)
    if span_letters < MIN_SPAN_LETTERS:
        record.junk, record.junk_why = True, f"purpose_span has {span_letters} letters (< {MIN_SPAN_LETTERS})"
    if score < QUOTE_THRESHOLD:
        return _reject(profile, record, "rejected_not_verbatim")
    if record.junk:
        return _reject(profile, record, "rejected_junk")
    reason = containing_sentences(excerpt, start, end)
    data = profile.model_dump()
    data.update(reason=reason, reason_source="expert_verbal", status="in_review")
    try:
        updated = WorkProfile.model_validate(data)
        validate_against_contract(updated)
    except (ValidationError, ValueError) as exc:
        log.warning("propose-reasons: %s rejected by the contract: %s", profile.profile_id, exc)
        return _reject(profile, record, "rejected_contract")
    record.decision, record.reason = "accepted", reason
    return updated


def locate(span: str, excerpt: str) -> tuple[float, int, int]:
    """How verbatim ``span`` is in ``excerpt`` (0-100, lowercased) and the excerpt range it matched.

    The range is narrowed to the characters that actually matched (edge runs of one character and
    surrounding spaces/punctuation dropped): ``partial_ratio``'s window is as long as the span, so
    an extra word in the span pushes it into the next or previous sentence (AC-26).
    """
    folded_span, folded = _fold(span), _fold(excerpt)
    if len(folded_span) > len(folded):  # partial_ratio would score the excerpt inside the span
        score, start, end = fuzz.ratio(folded_span, folded), 0, len(folded)
    else:
        match = fuzz.partial_ratio_alignment(folded_span, folded)  # offsets: in excerpt
        if match is None:
            return 0.0, 0, 0
        score, start, end = match.score, match.dest_start, match.dest_end
    same = [op for op in Indel.opcodes(folded_span, folded[start:end]) if op.tag == "equal"]
    solid = [op for op in same if op.dest_end - op.dest_start > 1] or same
    if solid:
        start, end = start + solid[0].dest_start, start + solid[-1].dest_end
    while start < end and not excerpt[start].isalnum():
        start += 1
    while end > start and not excerpt[end - 1].isalnum():
        end -= 1
    return float(score), start, end


def containing_sentences(excerpt: str, start: int, end: int) -> str:
    """The sentence(s) of ``excerpt`` overlapping ``excerpt[start:end]``, copied verbatim."""
    bounds: list[tuple[int, int]] = []
    begin = 0
    for brk in _SENTENCE_BREAK.finditer(excerpt):
        bounds.append((begin, brk.start()))
        begin = brk.end()
    bounds.append((begin, len(excerpt)))
    hit = [(s, e) for s, e in bounds if s < max(end, start + 1) and start < e]
    if not hit:
        return excerpt.strip()
    return excerpt[hit[0][0] : hit[-1][1]].strip()


def _prompt(profile: WorkProfile, excerpt: str) -> str:
    return render_prompt(
        "propose_reason.md",
        process_id=profile.process_id,
        step=profile.step,
        key_point=profile.key_point or "không có",
        transcript=excerpt,
    )


def _reject(profile: WorkProfile, record: ReasonAuditRecord, decision: ReasonDecision) -> WorkProfile:
    record.decision = decision
    return profile


def _fold(text: str) -> str:
    """Lowercase, one character for one, so match offsets are offsets in the original text."""
    return "".join(low if len(low := char.lower()) == 1 else char for char in text)


def _write(record: ReasonAuditRecord, audit: Path | None) -> None:
    log.info(
        "propose-reasons: %s %s (has_reason=%s, span=%r, score=%s, junk=%s)",
        record.profile_id,
        record.decision,
        record.has_reason,
        record.purpose_span,
        record.match_score,
        record.junk_why or False,
    )
    if audit is None:
        return
    with _AUDIT_LOCK:  # the API job may propose for several steps at once (KNOWHOW_VLM_CONCURRENCY)
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
