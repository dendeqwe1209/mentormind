"""Blur faces in frames that go to a cloud VLM — the image side of the outbound guard.

Text PII is masked by ``mentormind.core.guard``; in video the personal data is the worker's face.
Frames bound for a cloud provider are passed through YuNet (OpenCV's built-in face detector, model
~230 KB, MIT licence) and every face box is pixelated. Self-hosted calls keep the original frames.

The model is fetched once into ``KNOWHOW_GUARD_FACE_MODEL`` and verified by SHA-256. If it cannot
be loaded the call is refused (fail closed); ``KNOWHOW_GUARD_BLUR_FACES=false`` opts out.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path

import cv2
import httpx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
JPEG_QUALITY = 90

#: A face box in pixels: (x, y, width, height).
Box = tuple[int, int, int, int]
Detector = Callable[[np.ndarray], Sequence[Box]]


class FaceBlurError(RuntimeError):
    """Faces could not be checked, so the frames must not go to the cloud."""


class ImageGuardPolicy(BaseModel):
    """How frames bound for a cloud provider are anonymised (``KNOWHOW_GUARD_*``)."""

    model_config = ConfigDict(frozen=True)

    blur_faces: bool = True
    face_model: Path = Path("data/work/models/face_detection_yunet_2023mar.onnx")
    score_threshold: float = Field(default=0.6, gt=0, lt=1)


def ensure_face_model(path: Path) -> Path:
    """Return ``path``, downloading and verifying the YuNet model first if it is missing."""
    if path.is_file() and _sha256(path.read_bytes()) == YUNET_SHA256:
        return path
    try:
        response = httpx.get(YUNET_URL, follow_redirects=True, timeout=60)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FaceBlurError(
            f"Không tải được model làm mờ mặt ({exc!r}). Tải thủ công {YUNET_URL} về {path}, "
            "hoặc đặt KNOWHOW_GUARD_BLUR_FACES=false (chỉ với dữ liệu public)."
        ) from exc
    if _sha256(response.content) != YUNET_SHA256:
        raise FaceBlurError("Model làm mờ mặt tải về sai checksum SHA-256 — từ chối dùng.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(response.content)
    tmp.replace(path)
    return path


def yunet_detector(model: Path, score_threshold: float) -> Detector:
    """Face detector backed by ``cv2.FaceDetectorYN``."""
    try:
        net = cv2.FaceDetectorYN.create(str(model), "", (320, 320), score_threshold, 0.3, 50)
    except cv2.error as exc:
        raise FaceBlurError(f"Không nạp được model làm mờ mặt {model}: {exc}") from exc

    def detect(image: np.ndarray) -> list[Box]:
        height, width = image.shape[:2]
        net.setInputSize((width, height))
        _, faces = net.detect(image)
        if faces is None:
            return []
        return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces[:, :4]]

    return detect


class FaceBlurrer:
    """Pixelates every detected face in a JPEG/PNG frame."""

    def __init__(self, detector: Detector) -> None:
        self._detect = detector

    @classmethod
    def from_policy(cls, policy: ImageGuardPolicy) -> FaceBlurrer:
        model = ensure_face_model(policy.face_model)
        return cls(yunet_detector(model, policy.score_threshold))

    def blur(self, data: bytes) -> tuple[bytes, int]:
        """Return the frame re-encoded as JPEG with faces pixelated, and the face count."""
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FaceBlurError("Không đọc được khung hình để làm mờ mặt.")
        boxes = list(self._detect(image))
        for box in boxes:
            _pixelate(image, box)
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            raise FaceBlurError("Không mã hóa lại được khung hình sau khi làm mờ.")
        return encoded.tobytes(), len(boxes)


def _pixelate(image: np.ndarray, box: Box, margin: float = 0.25, cells: int = 6) -> None:
    x, y, w, h = box
    pad_w, pad_h = int(w * margin), int(h * margin)
    height, width = image.shape[:2]
    x0, y0 = max(0, x - pad_w), max(0, y - pad_h)
    x1, y1 = min(width, x + w + pad_w), min(height, y + h + pad_h)
    if x1 <= x0 or y1 <= y0:
        return
    region = image[y0:y1, x0:x1]
    small = cv2.resize(region, (cells, cells), interpolation=cv2.INTER_LINEAR)
    image[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
