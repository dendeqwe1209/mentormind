"""LeakGuard — the last safety net before a cloud call (bankassist-mcp SPEC §5).

Runs on the text that is about to be sent, AFTER masking. It must catch the case where masking
was forgotten or broken (bankassist test G-09: a no-op masker must still be blocked): any
recognizer hit, or any real value the vault knows about, means the call is refused.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from mentormind.core.guard.pii.recognizers import DEFAULT_RECOGNIZERS, Recognizer


class SensitiveDataLeakError(PermissionError):
    """Refused to send text that still has sensitive data. Carries the kind, never the value."""

    def __init__(self, kind: str) -> None:
        super().__init__(
            f"Không thể gửi yêu cầu ra provider cloud: phát hiện dữ liệu nhạy cảm chưa được che "
            f"({kind}). Sự việc đã được ghi nhận."
        )
        self.kind = kind


class LeakGuard:
    def __init__(
        self,
        recognizers: Sequence[Recognizer] = DEFAULT_RECOGNIZERS,
        known_values: Iterable[str] = (),
    ) -> None:
        self._recognizers = tuple(recognizers)
        self._known = [value.casefold() for value in known_values if value.strip()]

    def check(self, text: str) -> str | None:
        """Kind of the first residue found in ``text`` (e.g. ``"PHONE"``), or None when clean."""
        if not text:
            return None
        folded = text.casefold()
        if any(value in folded for value in self._known):
            return "KNOWN_VALUE"
        for recognizer in self._recognizers:
            if recognizer.find(text):
                return recognizer.entity
        return None

    def ensure_clean(self, texts: Iterable[str | None]) -> None:
        """Raise :class:`SensitiveDataLeakError` if any of ``texts`` is not clean."""
        for text in texts:
            kind = self.check(text or "")
            if kind is not None:
                raise SensitiveDataLeakError(kind)
