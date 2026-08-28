"""Deterministic checks for minimal Teacher Role scope and provenance."""

from __future__ import annotations

import unittest

from search_harness.evolution.research.roles.provenance import (
    base_prompt_digest,
    input_view_digest,
    model_input_view,
    teacher_role_scope_from_artifact,
)
from search_harness.evolution.research.roles.spec import TeacherPromptSpec


class TeacherRoleProvenanceTest(unittest.TestCase):
    def test_scope_projects_only_role_contract_and_model_identity(self) -> None:
        artifact = {
            "role": {"id": "compiler", "version": 3},
            "model": {
                "provider": "openai_compatible",
                "model_id": "teacher-a",
                "temperature": 0.2,
                "max_tokens": 4096,
            },
            "output_contract": {
                "id": "compiler_result",
                "version": 8,
                "schema_digest": "not-a-scope-field",
            },
            "base_prompt_digest": "audit-only",
            "input_view_digest": "audit-only",
        }

        scope = teacher_role_scope_from_artifact(artifact)

        self.assertEqual(scope.role_id, "compiler")
        self.assertEqual(scope.role_contract_version, 3)
        self.assertEqual(scope.model_provider, "openai_compatible")
        self.assertEqual(scope.model_id, "teacher-a")
        self.assertFalse(hasattr(scope, "base_prompt_digest"))
        self.assertFalse(hasattr(scope, "output_contract"))

    def test_prompt_digest_depends_on_content_not_location(self) -> None:
        first = TeacherPromptSpec(
            instructions="Inspect the evidence.",
            user_template=(
                "{{role_input}}\n{{resource_context}}"
            ),
            continuation_templates={
                "review": "Feedback: {{feedback_event}}"
            },
        )
        second = TeacherPromptSpec(
            instructions="Inspect the evidence.",
            user_template=(
                "{{role_input}}\n{{resource_context}}"
            ),
            continuation_templates={
                "review": "Feedback: {{feedback_event}}"
            },
        )
        changed = TeacherPromptSpec(
            instructions="Inspect all evidence.",
            user_template=(
                "{{role_input}}\n{{resource_context}}"
            ),
            continuation_templates={
                "review": "Feedback: {{feedback_event}}"
            },
        )

        self.assertEqual(base_prompt_digest(first), base_prompt_digest(second))
        self.assertNotEqual(
            base_prompt_digest(first),
            base_prompt_digest(changed),
        )

    def test_input_digest_uses_only_detached_model_visible_view(self) -> None:
        messages = [
            {"role": "system", "content": "Base role prompt"},
            {"role": "user", "content": "Compact role input"},
        ]
        view = model_input_view(messages=messages, tools=())
        digest = input_view_digest([view])

        messages[1]["content"] = "mutated after snapshot"

        self.assertEqual(digest, input_view_digest([view]))
        self.assertNotEqual(
            digest,
            input_view_digest(
                [
                    model_input_view(
                        messages=[
                            {"role": "system", "content": "Base role prompt"},
                            {"role": "user", "content": "Different compact input"},
                        ],
                        tools=(),
                    )
                ]
            ),
        )
        self.assertNotIn("resource_config", view)


if __name__ == "__main__":
    unittest.main()
