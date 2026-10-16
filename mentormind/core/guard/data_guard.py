"""DataGuard — constitution art. 2 enforced in code, not by discipline (spec 01 FR-09).

``factory_confidential`` data must never reach a provider whose ``is_cloud`` is True. Every
provider call path checks here BEFORE touching the data (spec 04 FR-02).
"""

from __future__ import annotations

from typing import Protocol

from mentormind.core.schemas.common import DataClassification


class SupportsCloudFlag(Protocol):
    """Anything data can be sent to: a provider declares whether it leaves the premises."""

    @property
    def name(self) -> str: ...

    @property
    def is_cloud(self) -> bool: ...


class ConfidentialDataError(PermissionError):
    """Refused to send factory-confidential data to a cloud provider."""


class DataGuard:
    """Gatekeeper between classified data and providers."""

    @staticmethod
    def check(classification: DataClassification | str, provider: SupportsCloudFlag) -> None:
        """Raise :class:`ConfidentialDataError` if ``classification`` may not go to ``provider``.

        Args:
            classification: Label of the data about to be sent.
            provider: Destination; only its ``is_cloud`` flag matters.

        Raises:
            ConfidentialDataError: ``factory_confidential`` data and a cloud provider.
            ValueError: ``classification`` is not a known label (fail closed).
        """
        label = DataClassification(classification)
        if label is DataClassification.FACTORY_CONFIDENTIAL and provider.is_cloud:
            raise ConfidentialDataError(
                f"Chặn gửi dữ liệu factory_confidential tới provider cloud '{provider.name}'. "
                "Dữ liệu nhà máy chỉ được xử lý bằng provider self-host (vd. local_openai)."
            )
