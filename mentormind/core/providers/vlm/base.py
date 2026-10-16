"""VLM provider interface (spec 04 §2).

:meth:`VLMProvider.generate` is a template method, so no provider can skip a guard:

1. ``DataGuard.check`` — confidential data never reaches a cloud provider, checked BEFORE any
   frame file is opened (constitution art. 2, spec 04 FR-02 / AC-03);
2. for a cloud provider only (spec 01 FR-09b, spec 04 FR-02c): PII in the prompt is masked,
   LeakGuard re-scans it, faces in the frames are pixelated, the answer's tokens are restored
   and the call is audited;
3. the subclass's :meth:`VLMProvider._complete` talks to the model.
"""

from __future__ import annotations

import threading
import time
from abc import abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Literal

from mentormind.core.guard import GuardPolicy, OutboundSession
from mentormind.core.guard.image import FaceBlurrer, ImageGuardPolicy
from mentormind.core.providers.base import ProviderBase
from mentormind.core.providers.errors import ProviderError
from mentormind.core.providers.models import TokenUsage
from mentormind.core.providers.parsing import parse_json_object
from mentormind.core.providers.vlm.models import ImageInput, VLMResponse
from mentormind.core.schemas.common import DataClassification

_MIME_BY_SUFFIX: dict[str, Literal["image/jpeg", "image/png"]] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def read_image(path: Path) -> ImageInput:
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower())
    if mime is None:
        raise ProviderError(f"Unsupported frame format {path.suffix!r}: {path}")
    return ImageInput(path=path, mime_type=mime, data=path.read_bytes())


class VLMProvider(ProviderBase):
    """Describes a sequence of frames. Subclass, then ``@register_vlm("name")``."""

    kind: ClassVar[str] = "VLM"

    #: Model id sent to the endpoint (goes into ``model_info.model``).
    model: str
    #: Outbound guard for cloud calls; ``get_vlm_provider`` sets both from ``KNOWHOW_GUARD_*``.
    guard_policy: GuardPolicy = GuardPolicy()
    image_policy: ImageGuardPolicy = ImageGuardPolicy()
    #: Built on first cloud call from ``image_policy``; tests inject one with a fake detector.
    face_blurrer: FaceBlurrer | None = None

    def generate(
        self,
        frames: Sequence[Path],
        prompt: str,
        *,
        classification: DataClassification | str,
        json_schema: Mapping[str, Any] | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> VLMResponse:
        """Send ``frames`` (in time order) plus ``prompt``; return the raw answer.

        Raises:
            ConfidentialDataError: ``classification`` may not leave the premises via this
                provider — raised before any frame file is opened.
            SensitiveDataLeakError: a cloud call would still carry PII after masking.
            FaceBlurError: faces could not be checked for a cloud call (fail closed).
            ProviderError: transport/HTTP failure or unexpected response shape.
        """
        session = OutboundSession(self.guard_policy, self, classification, kind=self.kind, model=self.model)
        images = [read_image(Path(p)) for p in frames]
        outgoing_prompt = session.mask(prompt) or ""
        outgoing_system = session.mask(system)
        session.ensure_clean([outgoing_prompt, outgoing_system], frames=len(images))
        faces = 0
        if self.is_cloud and self.image_policy.blur_faces and images:
            images, faces = self._blur_faces(images)
        started = time.perf_counter()
        text, usage = self._complete(
            images,
            outgoing_prompt,
            json_schema=json_schema,
            system=outgoing_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latency = time.perf_counter() - started
        session.audit(frames=len(images), faces_blurred=faces, duration_ms=round(latency * 1000))
        return VLMResponse(
            text=session.restore(text),
            usage=usage,
            latency_s=latency,
            provider=self.name,
            model=self.model,
        )

    def _blur_faces(self, images: list[ImageInput]) -> tuple[list[ImageInput], int]:
        # One blur at a time per provider: the face detector (one cv2.FaceDetectorYN) is not
        # thread-safe, and a job may call generate from several threads (KNOWHOW_VLM_CONCURRENCY).
        with _face_blur_lock(self):
            if self.face_blurrer is None:
                self.face_blurrer = FaceBlurrer.from_policy(self.image_policy)
            blurred, total = [], 0
            for image in images:
                data, count = self.face_blurrer.blur(image.data)
                blurred.append(ImageInput(path=image.path, mime_type="image/jpeg", data=data))
                total += count
            return blurred, total

    def generate_json(
        self,
        frames: Sequence[Path],
        prompt: str,
        json_schema: Mapping[str, Any],
        *,
        classification: DataClassification | str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Like :meth:`generate`, parsed as a JSON object (spec 04 §2 surface).

        Raises:
            InvalidJSONError: the answer is not a JSON object (``raw_text`` keeps it).
        """
        response = self.generate(
            frames,
            prompt,
            classification=classification,
            json_schema=json_schema,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return parse_json_object(response.text)

    @abstractmethod
    def _complete(
        self,
        images: Sequence[ImageInput],
        prompt: str,
        *,
        json_schema: Mapping[str, Any] | None,
        system: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, TokenUsage | None]:
        """Call the model once; return its text and token usage (None when unreported)."""


_FACE_BLUR_LOCKS = threading.Lock()


def _face_blur_lock(provider: VLMProvider) -> threading.Lock:
    """The provider's own face-blur lock, created on first use (subclasses need no ``__init__`` call)."""
    with _FACE_BLUR_LOCKS:
        lock = provider.__dict__.get("_face_blur_lock")
        if lock is None:
            lock = provider.__dict__["_face_blur_lock"] = threading.Lock()
        return lock
