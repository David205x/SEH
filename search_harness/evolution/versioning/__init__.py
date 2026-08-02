"""In-memory Harness evolution workspaces and accepted Git versions."""

from .policy import (
    ComponentEvolutionPolicy,
    EvolutionPolicy,
    load_evolution_policy,
)
from .store import TemplateVersionStore, VersionRecord
from .journal import CandidateAttemptEvent, CandidateAttempt, CandidateAttemptState
from .validation import HarnessValidator, ValidationReport, stage_files
from .workspace import (
    CandidateWorkspace,
    FileEdit,
    HarnessSnapshot,
    content_digest,
    normalize_template_path,
)

__all__ = [
    "CandidateWorkspace",
    "ComponentEvolutionPolicy",
    "EvolutionPolicy",
    "FileEdit",
    "HarnessSnapshot",
    "content_digest",
    "HarnessValidator",
    "TemplateVersionStore",
    "CandidateAttemptEvent",
    "CandidateAttempt",
    "CandidateAttemptState",
    "ValidationReport",
    "VersionRecord",
    "normalize_template_path",
    "load_evolution_policy",
    "stage_files",
]
