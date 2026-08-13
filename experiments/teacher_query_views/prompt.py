"""Shadow prompt adapters that change presentation, not role semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from search_harness.evolution.research.roles.contracts import TeacherPayload
from search_harness.evolution.research.roles.spec import TeacherPromptSpec

from .views import render_evidence_reviewer_input
from .views import render_mechanism_distiller_input
from .compiler import render_shadow_compiler_input
from .candidate import render_shadow_candidate_input


@dataclass(frozen=True)
class ShadowEvidenceReviewerPrompt(TeacherPromptSpec):
    """Keep formal instructions while rendering a compact initial input."""

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        return render_evidence_reviewer_input(
            role_input.model_dump(mode="json"),
            resource_context,
        )


@dataclass(frozen=True)
class ShadowMechanismDistillerPrompt(TeacherPromptSpec):
    """Render one complete Distiller dossier over attached immutable trials."""

    trial_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        return render_mechanism_distiller_input(
            role_input.model_dump(mode="json"),
            self.trial_payloads,
            resource_context,
        )


@dataclass(frozen=True)
class ShadowCompilerPrompt(TeacherPromptSpec):
    """Render a complete authoring brief without narrowing Compiler access."""

    parent_authoring: dict[str, Any] = field(default_factory=dict)

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        context = dict(resource_context)
        compiler = context.get("compiler")
        compiler = dict(compiler) if isinstance(compiler, dict) else {}
        compiler.update(self.parent_authoring)
        context["compiler"] = compiler
        return render_shadow_compiler_input(
            role_input.model_dump(mode="json"),
            context,
        )


@dataclass(frozen=True)
class ShadowCandidateReviewerPrompt(TeacherPromptSpec):
    """Render one non-duplicated Candidate decision brief."""

    def render_input(
        self,
        role_input: TeacherPayload,
        resource_context: dict[str, Any],
    ) -> str:
        return render_shadow_candidate_input(
            role_input.model_dump(mode="json"),
            resource_context,
        )
