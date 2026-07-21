"""Small result contract for standalone Intervention coordination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


InterventionVerdict = Literal["supported", "rejected", "inconclusive"]


@dataclass(frozen=True)
class InterventionCoordinatorResult:
    """Coordinator analysis and the single Worker trial it recommends."""

    analysis: str
    verdict: InterventionVerdict
    selected_trial_id: str | None
    recommendation: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InterventionCoordinatorResult":
        expected = {"analysis", "verdict", "selected_trial_id", "recommendation"}
        missing = expected - set(payload)
        if missing:
            raise ValueError(
                f"coordinator result lacks required fields: {sorted(missing)}"
            )
        unknown = set(payload) - expected
        if unknown:
            raise ValueError(
                f"coordinator result has unsupported fields: {sorted(unknown)}"
            )
        analysis = payload.get("analysis")
        verdict = payload.get("verdict")
        selected_trial_id = payload.get("selected_trial_id")
        recommendation = payload.get("recommendation")
        if not isinstance(analysis, str) or not analysis.strip():
            raise ValueError("coordinator analysis must be a non-empty string")
        if verdict not in {"supported", "rejected", "inconclusive"}:
            raise ValueError(
                "coordinator verdict must be supported, rejected or inconclusive"
            )
        if selected_trial_id is not None and (
            not isinstance(selected_trial_id, str) or not selected_trial_id.strip()
        ):
            raise ValueError("selected_trial_id must be a non-empty string or null")
        if not isinstance(recommendation, str) or not recommendation.strip():
            raise ValueError("coordinator recommendation must be a non-empty string")
        return cls(
            analysis=analysis.strip(),
            verdict=verdict,
            selected_trial_id=(
                selected_trial_id.strip()
                if isinstance(selected_trial_id, str)
                else None
            ),
            recommendation=recommendation.strip(),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "analysis": self.analysis,
            "verdict": self.verdict,
            "selected_trial_id": self.selected_trial_id,
            "recommendation": self.recommendation,
        }
