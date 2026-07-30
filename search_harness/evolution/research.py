"""Evidence-driven research records persisted beside one evolution run."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


CapabilityStatus = Literal["supported", "partial", "unsupported", "unknown"]
ObligationStatus = Literal["open", "satisfied", "falsified", "abandoned"]
IterationProductKind = Literal[
    "evidence_recorded",
    "hypothesis_rejected",
    "more_evidence_required",
    "ready_for_distillation",
    "candidate_compiled",
    "candidate_accepted",
    "candidate_rejected",
]


@dataclass(frozen=True)
class CapabilityObservation:
    """One experimentally observed Actor capability."""

    capability: str
    status: CapabilityStatus
    observation: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ActorCapabilityProfile:
    """Reusable capability evidence bound to one model and Harness digest."""

    profile_id: str
    actor_model: str
    harness_digest: str
    observations: tuple[CapabilityObservation, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationContract:
    """Metrics and falsification criteria frozen before running a hypothesis."""

    contract_id: str
    hypothesis_ref: str
    core_metrics: tuple[str, ...]
    mechanism_metrics: tuple[str, ...]
    expected_effect: str
    falsifier: str
    replicate_count: int
    sample_scope: str

    def __post_init__(self) -> None:
        if self.replicate_count < 1:
            raise ValueError("replicate_count must be positive")
        if not self.core_metrics:
            raise ValueError("evaluation contract requires core_metrics")
        if not self.mechanism_metrics:
            raise ValueError("evaluation contract requires mechanism_metrics")


@dataclass(frozen=True)
class EvidenceObligation:
    """One falsifiable question that controls the next evidence-gathering step."""

    obligation_id: str
    hypothesis_ref: str
    question: str
    status: ObligationStatus = "open"
    evidence_refs: tuple[str, ...] = ()
    resolution: str | None = None

    def __post_init__(self) -> None:
        if self.status == "open" and self.resolution is not None:
            raise ValueError("open evidence obligation cannot have a resolution")
        if self.status != "open" and not self.resolution:
            raise ValueError("closed evidence obligation requires a resolution")


@dataclass(frozen=True)
class IterationProduct:
    """A useful research result produced by one bounded iteration."""

    iteration: int
    kind: IterationProductKind
    summary: str
    artifact_refs: tuple[str, ...] = ()
    next_obligation: str | None = None

    def __post_init__(self) -> None:
        if self.iteration < 1:
            raise ValueError("iteration must be positive")
        if self.kind == "more_evidence_required" and not self.next_obligation:
            raise ValueError(
                "more_evidence_required product requires next_obligation"
            )


class EvolutionResearchStore:
    """Append-only persistence for reusable research state and iteration products."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def record_capability_profile(self, profile: ActorCapabilityProfile) -> None:
        """Persist one capability profile after rejecting duplicate IDs."""

        self._ensure_new_id(
            self.root / "capability_profiles.jsonl", "profile_id", profile.profile_id
        )
        self._append("capability_profiles.jsonl", asdict(profile))

    def record_evaluation_contract(self, contract: EvaluationContract) -> None:
        """Persist one immutable pre-trial evaluation contract."""

        self._ensure_new_id(
            self.root / "evaluation_contracts.jsonl",
            "contract_id",
            contract.contract_id,
        )
        self._append("evaluation_contracts.jsonl", asdict(contract))

    def open_obligation(self, obligation: EvidenceObligation) -> None:
        """Open a new evidence obligation."""

        if obligation.status != "open":
            raise ValueError("new evidence obligation must be open")
        current = self._latest_obligations().get(obligation.obligation_id)
        if current == obligation:
            return
        if current is not None:
            raise ValueError(
                f"duplicate obligation_id: {obligation.obligation_id}"
            )
        self._append("evidence_obligations.jsonl", asdict(obligation))

    def resolve_obligation(
        self,
        obligation_id: str,
        *,
        status: Literal["satisfied", "falsified", "abandoned"],
        resolution: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> EvidenceObligation:
        """Close an existing obligation while preserving its event history."""

        current = self._latest_obligations().get(obligation_id)
        if current is None:
            raise KeyError(f"unknown evidence obligation: {obligation_id}")
        if current.status != "open":
            raise ValueError(f"evidence obligation is already {current.status}")
        resolved = EvidenceObligation(
            obligation_id=current.obligation_id,
            hypothesis_ref=current.hypothesis_ref,
            question=current.question,
            status=status,
            evidence_refs=evidence_refs,
            resolution=resolution,
        )
        self._append("evidence_obligations.jsonl", asdict(resolved))
        return resolved

    def list_open_obligations(self) -> tuple[EvidenceObligation, ...]:
        """Return the latest state of every currently open obligation."""

        return tuple(
            obligation
            for obligation in self._latest_obligations().values()
            if obligation.status == "open"
        )

    def record_mechanism(
        self,
        *,
        mechanism_ref: str,
        mechanism: dict[str, Any],
        evidence_refs: tuple[str, ...],
    ) -> None:
        """Persist one validated mechanism specification by reference."""

        path = self.root / "mechanism_specs.jsonl"
        self._ensure_new_id(path, "mechanism_ref", mechanism_ref)
        self._append(
            "mechanism_specs.jsonl",
            {
                "mechanism_ref": mechanism_ref,
                "mechanism": mechanism,
                "evidence_refs": evidence_refs,
            },
        )

    def record_iteration_product(self, product: IterationProduct) -> None:
        """Persist a research product without treating it as a run terminator."""

        path = self.root / "iteration_products.jsonl"
        payload = asdict(product)
        if any(
            {
                "iteration": item.get("iteration"),
                "kind": item.get("kind"),
                "artifact_refs": item.get("artifact_refs", []),
            }
            == {
                "iteration": payload["iteration"],
                "kind": payload["kind"],
                "artifact_refs": list(payload["artifact_refs"]),
            }
            for item in self._read(path)
        ):
            return
        self._append("iteration_products.jsonl", asdict(product))

    def _latest_obligations(self) -> dict[str, EvidenceObligation]:
        latest: dict[str, EvidenceObligation] = {}
        for payload in self._read(self.root / "evidence_obligations.jsonl"):
            payload["evidence_refs"] = tuple(payload.get("evidence_refs", ()))
            obligation = EvidenceObligation(**payload)
            latest[obligation.obligation_id] = obligation
        return latest

    def _ensure_new_id(self, path: Path, field: str, value: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be empty")
        if any(payload.get(field) == value for payload in self._read(path)):
            raise ValueError(f"duplicate {field}: {value}")

    def _append(self, filename: str, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": 1,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with (self.root / filename).open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _read(path: Path) -> tuple[dict[str, Any], ...]:
        if not path.is_file():
            return ()
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise TypeError(f"{path}:{line_number}: record must be an object")
            payload.pop("schema_version", None)
            payload.pop("recorded_at", None)
            records.append(payload)
        return tuple(records)
