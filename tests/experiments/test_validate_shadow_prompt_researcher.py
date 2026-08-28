"""Shadow Prompt Researcher experiment entrypoint tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from experiments.validate_shadow_prompt_researcher import (
    _inline_shadow_mechanism,
    _parse_args,
)


class ValidateShadowPromptResearcherTest(unittest.TestCase):
    def test_mechanism_artifact_is_optional(self) -> None:
        args = _parse_args(
            [
                "--distiller-artifact",
                "distiller.json",
                "--output-dir",
                "runs/experiments/prompt",
            ]
        )

        self.assertIsNone(args.mechanism_artifact)
        self.assertEqual(args.distiller_artifact, Path("distiller.json"))

    def test_extracts_inline_distilled_mechanism(self) -> None:
        mechanism = {
            "effect": {
                "kind": "behavioral_intermediate",
                "success": "The Student searches again.",
            },
            "phases": [],
            "state": [],
            "constraints": [],
        }

        extracted = _inline_shadow_mechanism(
            {
                "output": {
                    "outcome": "distilled",
                    "mechanism": mechanism,
                }
            }
        )

        self.assertEqual(extracted, mechanism)
        self.assertIsNot(extracted, mechanism)


if __name__ == "__main__":
    unittest.main()
