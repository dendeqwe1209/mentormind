"""spec 01 AC-10, AC-11 — the per-call outbound chain: refuse leaks, audit counts only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from mentormind.core.guard import (
    GuardPolicy,
    OutboundSession,
    SensitiveDataLeakError,
)


class Destination(BaseModel):
    name: str
    is_cloud: bool


CLOUD = Destination(name="qwen_api", is_cloud=True)


LOCAL = Destination(name="local_openai", is_cloud=False)


def test_ac_10_disabled_masking_is_still_blocked_and_audited(tmp_path: Path) -> None:
    # G-09: the "no-op masker" case — masking switched off must not let PII through.
    policy = GuardPolicy(mask_text=False, audit_dir=tmp_path)
    session = OutboundSession(policy, CLOUD, "public", kind="VLM", model="m")
    with pytest.raises(SensitiveDataLeakError) as info:
        session.ensure_clean(["gọi 0987654321"], frames=3)
    assert "0987654321" not in str(info.value)  # G-05: neutral message
    [line] = (tmp_path).glob("outbound-*.jsonl").__next__().read_text().splitlines()
    record = json.loads(line)
    assert record["level"] == "SecurityAlert" and record["detected_kind"] == "PHONE"  # G-06
    assert "0987654321" not in line  # G-07


def test_ac_11_audit_records_counts_never_values(tmp_path: Path) -> None:
    policy = GuardPolicy(audit_dir=tmp_path, known_entities={"PERSON": ["Nguyễn Văn An"]})
    session = OutboundSession(policy, CLOUD, "synthetic", kind="VLM", model="qwen3-vl-8b")
    masked = session.mask("Nguyễn Văn An: gọi 0987654321") or ""
    session.ensure_clean([masked])
    session.audit(frames=12, faces_blurred=2, duration_ms=850)
    line = next(tmp_path.glob("outbound-*.jsonl")).read_text().strip()
    record = json.loads(line)
    assert record["masked_counts"] == {"PERSON": 1, "PHONE": 1}
    assert (record["frames"], record["faces_blurred"], record["level"]) == (12, 2, "Info")
    assert "0987654321" not in line and "Nguyễn" not in line


def test_self_hosted_destination_gets_text_untouched_and_no_audit(tmp_path: Path) -> None:
    session = OutboundSession(GuardPolicy(audit_dir=tmp_path), LOCAL, "factory_confidential",
                              kind="VLM", model="m")  # fmt: skip
    text = "gọi 0987654321"
    assert session.mask(text) == text
    session.ensure_clean([text])
    session.audit()
    assert list(tmp_path.iterdir()) == []
