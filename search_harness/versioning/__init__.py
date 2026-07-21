"""In-memory Harness evolution workspaces and accepted Git versions."""

from .store import HarnessVersionStore, VersionRecord
from .journal import IterationEvent, IterationSession, IterationSummary
from .validation import HarnessValidator, ValidationReport, stage_files
from .workspace import (
    CandidateWorkspace,
    FileEdit,
    HarnessSnapshot,
    content_digest,
    normalize_plugin_path,
)

__all__ = [
    "CandidateWorkspace",
    "FileEdit",
    "HarnessSnapshot",
    "content_digest",
    "HarnessValidator",
    "HarnessVersionStore",
    "IterationEvent",
    "IterationSession",
    "IterationSummary",
    "ValidationReport",
    "VersionRecord",
    "normalize_plugin_path",
    "stage_files",
]
