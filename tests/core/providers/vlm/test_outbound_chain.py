"""spec 04 AC-16, AC-17 — cloud VLM calls get masked text and face-blurred frames."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from pydantic import SecretStr

from mentormind.core.config import Settings
from mentormind.core.guard import GuardPolicy, SensitiveDataLeakError
from mentormind.core.guard.image import FaceBlurError, FaceBlurrer, ImageGuardPolicy, face_blur
from mentormind.core.providers.vlm import get_vlm_provider
from mentormind.core.providers.vlm.backends.fake import FakeVLM
from tests.core.providers.fakes import RecordingHttp

FACE_BOX = (8, 8, 24, 24)


def fake_detector(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    return [FACE_BOX]


def noisy_frame(path: Path) -> Path:
    rng = np.random.default_rng(7)
    cv2.imwrite(str(path), rng.integers(0, 256, (64, 96, 3), dtype=np.uint8))
    return path


def test_ac_16_cloud_vlm_gets_masked_prompt_and_answer_is_restored(tmp_path: Path) -> None:
    vlm = FakeVLM(['{"note": "gọi [PHONE_1] nếu thiếu hàng"}'], name="qwen_api", is_cloud=True)
    vlm.guard_policy = GuardPolicy(audit_dir=tmp_path)
    vlm.image_policy = ImageGuardPolicy(blur_faces=False)
    response = vlm.generate([], "Tổ trưởng: 0987654321. Mô tả thao tác.", classification="public")
    assert vlm.calls[0].prompt == "Tổ trưởng: [PHONE_1]. Mô tả thao tác."
    assert json.loads(response.text) == {"note": "gọi 0987654321 nếu thiếu hàng"}
    record = json.loads(next(tmp_path.glob("outbound-*.jsonl")).read_text())
    assert record["provider"] == "qwen_api" and record["masked_counts"] == {"PHONE": 1}


def test_ac_16_self_hosted_vlm_gets_the_prompt_untouched() -> None:
    vlm = FakeVLM(is_cloud=False)
    vlm.generate([], "Tổ trưởng: 0987654321", classification="factory_confidential")
    assert vlm.calls[0].prompt == "Tổ trưởng: 0987654321"


def test_ac_16_leak_is_refused_before_any_http_call(settings: Settings, http: RecordingHttp) -> None:
    settings = settings.model_copy(
        update={
            "vlm_provider": "openrouter",
            "vlm_api_key": SecretStr("k"),
            "guard_mask_text": False,
        }
    )
    vlm = get_vlm_provider(settings, http=http)
    with pytest.raises(SensitiveDataLeakError):
        vlm.generate([], "gọi 0987654321", classification="public")
    assert http.posts == []


def test_ac_17_cloud_frames_are_face_blurred(tmp_path: Path) -> None:
    frame = noisy_frame(tmp_path / "f.jpg")
    vlm = FakeVLM(is_cloud=True, name="siliconflow")
    vlm.guard_policy = GuardPolicy(audit_dir=tmp_path / "audit")
    vlm.face_blurrer = FaceBlurrer(fake_detector)
    vlm.generate([frame], "mô tả", classification="public")

    sent = cv2.imdecode(np.frombuffer(vlm.calls[0].images[0].data, np.uint8), cv2.IMREAD_COLOR)
    original = cv2.imread(str(frame))
    assert sent is not None and original is not None
    x, y, w, h = FACE_BOX
    face_sent, face_orig = sent[y : y + h, x : x + w], original[y : y + h, x : x + w]
    assert face_sent.std() < face_orig.std() / 2  # pixelated: detail gone
    assert np.abs(sent[50:, 60:].astype(int) - original[50:, 60:]).mean() < 12  # rest kept
    record = json.loads(next((tmp_path / "audit").glob("outbound-*.jsonl")).read_text())
    assert record["faces_blurred"] == 1 and record["frames"] == 1


def test_ac_17_self_hosted_frames_are_sent_as_is(tmp_path: Path) -> None:
    frame = noisy_frame(tmp_path / "f.jpg")
    vlm = FakeVLM(is_cloud=False)
    vlm.face_blurrer = FaceBlurrer(fake_detector)
    vlm.generate([frame], "mô tả", classification="factory_confidential")
    assert vlm.calls[0].images[0].data == frame.read_bytes()


def test_ac_17_missing_face_model_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(face_blur.httpx, "get", offline)
    vlm = FakeVLM(is_cloud=True, name="qwen_api")
    vlm.guard_policy = GuardPolicy(audit_dir=None)
    vlm.image_policy = ImageGuardPolicy(face_model=tmp_path / "missing.onnx")
    with pytest.raises(FaceBlurError, match="KNOWHOW_GUARD_BLUR_FACES"):
        vlm.generate([noisy_frame(tmp_path / "f.jpg")], "mô tả", classification="public")
    assert vlm.calls == []
