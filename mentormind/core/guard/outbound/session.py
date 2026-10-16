"""OutboundGuard — the bankassist chain applied to every provider call (spec 01 FR-09b).

    DataGuard.check (block confidential)          — every destination
    -> PiiMasker (text)                           — cloud destinations, unless mask_text=False
    -> LeakGuard (second scan, refuse on residue) — cloud destinations, ALWAYS
    -> send -> restore tokens in the answer
    -> AuditLog (counts, SecurityAlert on refusal)

LeakGuard cannot be switched off: with ``mask_text=False`` a cloud call carrying PII is refused
instead of masked (bankassist test G-09). A self-hosted destination receives the data untouched:
it never leaves the premises.
"""

from __future__ import annotations

from collections.abc import Iterable

from mentormind.core.guard.data_guard import DataGuard, SupportsCloudFlag
from mentormind.core.guard.outbound.audit import AuditLog, AuditRecord
from mentormind.core.guard.outbound.policy import GuardPolicy
from mentormind.core.guard.pii import LeakGuard, PiiMasker, PiiVault, SensitiveDataLeakError
from mentormind.core.schemas.common import DataClassification


class OutboundSession:
    """Guard state of ONE call: its vault, what was masked, and the audit trail."""

    def __init__(
        self,
        policy: GuardPolicy,
        destination: SupportsCloudFlag,
        classification: DataClassification | str,
        *,
        kind: str,
        model: str,
    ) -> None:
        DataGuard.check(classification, destination)
        self._policy = policy
        self._destination = destination
        self._classification = str(DataClassification(classification))
        self._kind = kind
        self._model = model
        self._cloud = destination.is_cloud
        self._active = self._cloud and policy.mask_text
        self._masker = PiiMasker(PiiVault(), known=policy.known_entities, extra_patterns=policy.extra_patterns)
        self._audit = AuditLog(policy.audit_dir if destination.is_cloud else None)

    @property
    def active(self) -> bool:
        """True when text is masked (cloud destination and masking enabled)."""
        return self._active

    def mask(self, text: str | None) -> str | None:
        if text is None or not self._active:
            return text
        return self._masker.mask_text(text)

    def ensure_clean(self, texts: Iterable[str | None], *, frames: int = 0) -> None:
        """LeakGuard over the outgoing texts; on residue, audit a SecurityAlert and refuse."""
        if not self._cloud:
            return
        guard = LeakGuard(self._masker.recognizers, known_values=self._known_values())
        try:
            guard.ensure_clean(texts)
        except SensitiveDataLeakError as exc:
            self.audit(frames=frames, level="SecurityAlert", detected_kind=exc.kind)
            raise

    def restore(self, text: str) -> str:
        return self._masker.vault.restore(text) if self._active else text

    def masked_counts(self) -> dict[str, int]:
        return self._masker.vault.counts()

    def audit(
        self,
        *,
        frames: int = 0,
        faces_blurred: int = 0,
        duration_ms: int | None = None,
        level: str = "Info",
        detected_kind: str | None = None,
    ) -> None:
        self._audit.write(
            AuditRecord(
                kind=self._kind,
                provider=self._destination.name,
                model=self._model,
                classification=self._classification,
                frames=frames,
                masked_counts=self.masked_counts(),
                faces_blurred=faces_blurred,
                level="SecurityAlert" if level == "SecurityAlert" else "Info",
                detected_kind=detected_kind,
                duration_ms=duration_ms,
            )
        )

    def _known_values(self) -> list[str]:
        return [value for values in self._policy.known_entities.values() for value in values]
