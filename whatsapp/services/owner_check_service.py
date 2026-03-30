from __future__ import annotations

from dataclasses import dataclass

from telecom.models import PhoneLine


@dataclass(frozen=True)
class OwnerCheckResult:
    is_owner: bool
    stage: str


class MeowOwnerCheckService:
    OWNER_STAGE = "owner"
    NON_OWNER_STAGE = "non_owner"

    def check_number(self, phone_number: str) -> OwnerCheckResult:
        normalized_number = self._normalize_number(phone_number)
        if not normalized_number:
            return OwnerCheckResult(
                is_owner=False,
                stage=self.NON_OWNER_STAGE,
            )

        candidates = {
            normalized_number,
            f"+{normalized_number}",
        }
        line_exists = PhoneLine.objects.filter(phone_number__in=candidates).exists()
        if line_exists:
            return OwnerCheckResult(
                is_owner=True,
                stage=self.OWNER_STAGE,
            )

        return OwnerCheckResult(
            is_owner=False,
            stage=self.NON_OWNER_STAGE,
        )

    def _normalize_number(self, phone_number: str) -> str:
        return "".join(ch for ch in str(phone_number or "").strip() if ch.isdigit())
