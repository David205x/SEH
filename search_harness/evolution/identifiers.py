"""Canonical lifecycle identifiers for Harness evolution."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MAX_IDENTIFIER_LENGTH = 240


def validate_identifier(value: str, field_name: str = "identifier") -> str:
    """Validate one identifier that may also be used as a path component."""

    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"{field_name} exceeds {_MAX_IDENTIFIER_LENGTH} characters"
        )
    if _SAFE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must contain only letters, digits, '.', '-', or '_'"
        )
    return value


def new_run_id() -> str:
    """Create a readable, globally unique Controller Run identifier."""

    return f"run_{_utc_stamp()}_{uuid4().hex[:8]}"


def make_generation_id(run_id: str, generation: int) -> str:
    """Create the identity of one generation within a Controller Run."""

    return validate_identifier(
        f"{validate_identifier(run_id, 'run_id')}_g{_positive(generation, 'generation'):04d}",
        "generation_id",
    )


def make_research_attempt_id(
    generation_id: str,
    research_attempt: int,
) -> str:
    """Create the identity of one research attempt within a generation."""

    return validate_identifier(
        f"{validate_identifier(generation_id, 'generation_id')}_r"
        f"{_positive(research_attempt, 'research_attempt'):04d}",
        "research_attempt_id",
    )


def new_candidate_attempt_id() -> str:
    """Create a durable Candidate Attempt identifier."""

    return f"candidate_attempt_{_utc_stamp()}_{uuid4().hex[:8]}"


def make_failure_direction_id(
    generation_id: str,
    direction_index: int,
) -> str:
    """Create one generation-local Failure Direction identifier."""

    return validate_identifier(
        f"{validate_identifier(generation_id, 'generation_id')}_fd"
        f"{_positive(direction_index, 'direction_index'):04d}",
        "failure_direction_id",
    )


def make_research_scheme_id(
    failure_direction_id: str,
    scheme_index: int,
) -> str:
    """Create one Research Scheme identity under a Failure Direction."""

    return validate_identifier(
        f"{validate_identifier(failure_direction_id, 'failure_direction_id')}"
        f"_rs{_positive(scheme_index, 'scheme_index'):04d}",
        "research_scheme_id",
    )


def make_mechanism_scheme_id(research_scheme_id: str) -> str:
    """Create the stable Mechanism Scheme identity for a Research Scheme."""

    return validate_identifier(
        f"{validate_identifier(research_scheme_id, 'research_scheme_id')}_ms",
        "mechanism_scheme_id",
    )


def make_logical_work_id(
    research_attempt_id: str,
    work_index: int,
    work_kind: str,
) -> str:
    """Create one retry-stable logical work identifier."""

    safe_kind = validate_identifier(work_kind, "work_kind")
    return validate_identifier(
        f"{validate_identifier(research_attempt_id, 'research_attempt_id')}_w"
        f"{_positive(work_index, 'work_index'):04d}_{safe_kind}",
        "logical_work_id",
    )


def make_work_id(logical_work_id: str, attempt: int) -> str:
    """Create the identity of one physical execution attempt."""

    return validate_identifier(
        f"{validate_identifier(logical_work_id, 'logical_work_id')}_a"
        f"{_positive(attempt, 'attempt'):02d}",
        "work_id",
    )


def make_settlement_id(target_id: str, terminal_code: str) -> str:
    """Create a readable settlement key from its typed target and terminal."""

    return validate_identifier(
        f"{validate_identifier(target_id, 'settlement target')}_settlement_"
        f"{validate_identifier(terminal_code, 'terminal_code')}",
        "settlement_id",
    )


def make_version_id(index: int) -> str:
    """Create the ordered identity of one accepted Harness version."""

    return f"harness_v{_positive(index, 'version index'):04d}"


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _positive(value: int, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value
