"""Shadow Prompt Researcher packet, projection and product tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from search_harness.evolution.research.roles.contracts import (
    ShadowPromptResearcherInput,
    ShadowPromptResearchSubmission,
)
from search_harness.evolution.research.shadow_prompt_research import (
    ShadowPromptResearchResourceConfig,
    ShadowPromptResearchStore,
)


class ShadowPromptResearchTest(unittest.TestCase):
    def test_projects_reviewed_prefix_and_materializes_selected_prompt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollout = root / "rollout.jsonl"
            rollout.write_text(
                json.dumps(_rollout_record(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            env_file = root / ".env"
            env_file.write_text("", encoding="utf-8")
            trial_dir = root / "trial_001"
            trial_dir.mkdir()
            trial_file = trial_dir / "trial.json"
            trial_file.write_text(
                json.dumps(
                    {
                        "input": {
                            "example_id": "example-1",
                            "replicate_id": "r000",
                            "prefix_id": 9,
                        }
                    }
                ),
                encoding="utf-8",
            )
            role_input = ShadowPromptResearcherInput.model_validate(
                _role_input()
            )
            store = ShadowPromptResearchStore(
                config=ShadowPromptResearchResourceConfig(
                    rollout_file=rollout,
                    env_file=env_file,
                    max_cases=1,
                    repetitions=1,
                ),
                trial_files=[trial_file],
            )
            store.bind(role_input)

            case = store._cases[0]
            projected = {
                item["name"]: item["sources"][0]["value"]
                for item in case.projection["inputs"]
            }
            self.assertEqual(projected["question"], "Who wrote The Hobbit?")
            self.assertEqual(
                projected["interactions"][0]["tool_call"]["name"],
                "search",
            )
            self.assertEqual(
                projected["candidate"]["answer"],
                "Tolkien",
            )

            context = store.model_context()
            store._probes["shadow_prompt_probe_001"] = {
                "prompt": "Return one lowercase label.",
                "thinking_modes": ["enabled", "disabled"],
                "task_digest": context["task_digest"],
                "input_projection_digest": context[
                    "input_projection_digest"
                ],
                "prompt_review": {"decision": "supported"},
                "observations": [
                    {
                        "thinking_mode": "disabled",
                        "review": {"decision": "supported"},
                    }
                ],
            }
            result = store.materialize(
                ShadowPromptResearchSubmission(
                    outcome="ready",
                    prompt="Return one lowercase label.",
                    thinking_mode="disabled",
                    selected_probe_ref="shadow_prompt_probe_001",
                    obligation=None,
                )
            )

        self.assertEqual(result.outcome, "ready")
        self.assertIsNotNone(result.product)
        assert result.product is not None
        self.assertEqual(result.product.response_adapter, "tri_label")
        self.assertEqual(result.product.task_digest, context["task_digest"])

    def test_rejects_selected_mode_with_unsupported_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollout = root / "rollout.jsonl"
            rollout.write_text(
                json.dumps(_rollout_record()) + "\n",
                encoding="utf-8",
            )
            env_file = root / ".env"
            env_file.write_text("", encoding="utf-8")
            trial_dir = root / "trial_001"
            trial_dir.mkdir()
            trial_file = trial_dir / "trial.json"
            trial_file.write_text(
                json.dumps(
                    {
                        "input": {
                            "example_id": "example-1",
                            "replicate_id": "r000",
                            "prefix_id": 9,
                        }
                    }
                ),
                encoding="utf-8",
            )
            store = ShadowPromptResearchStore(
                config=ShadowPromptResearchResourceConfig(
                    rollout_file=rollout,
                    env_file=env_file,
                    max_cases=1,
                    repetitions=1,
                ),
                trial_files=[trial_file],
            )
            store.bind(ShadowPromptResearcherInput.model_validate(_role_input()))
            context = store.model_context()
            store._probes["shadow_prompt_probe_001"] = {
                "prompt": "Return one lowercase label.",
                "thinking_modes": ["disabled"],
                "task_digest": context["task_digest"],
                "input_projection_digest": context[
                    "input_projection_digest"
                ],
                "prompt_review": {"decision": "supported"},
                "observations": [
                    {
                        "thinking_mode": "disabled",
                        "review": {"decision": "unsupported"},
                    }
                ],
            }

            with self.assertRaises(ValueError):
                store.materialize(
                    ShadowPromptResearchSubmission(
                        outcome="ready",
                        prompt="Return one lowercase label.",
                        thinking_mode="disabled",
                        selected_probe_ref="shadow_prompt_probe_001",
                        obligation=None,
                    )
                )


def _role_input() -> dict[str, object]:
    return {
        "mechanism": {
            "effect": {
                "kind": "behavioral_intermediate",
                "success": "The Student searches again.",
            },
            "phases": [
                {
                    "phase": "pre_final",
                    "guards": ["stage.final_decision is present"],
                    "task": {
                        "kind": "decision",
                        "evaluator": "hook_model",
                        "inputs": [
                            {"name": "question", "sources": ["core.question"]},
                            {
                                "name": "interactions",
                                "sources": ["core.tool_interactions"],
                            },
                            {
                                "name": "candidate",
                                "sources": ["stage.final_decision"],
                            },
                        ],
                        "positive": "The answer lacks support.",
                        "negative": "The answer is directly supported.",
                        "uncertain": "The evidence cannot be resolved.",
                    },
                    "on_success": "Defer the final answer once.",
                    "fallback": {
                        "default": "continue_without_change",
                        "uncertain": None,
                        "exhausted": None,
                    },
                    "activation_limit": 1,
                }
            ],
            "state": [],
            "constraints": [],
        },
        "phase": "pre_final",
        "trial_reviews": [
            {
                "trial_ref": "trial_001",
                "predicate_observations": [
                    {
                        "phase": "pre_final",
                        "predicate_label": "negative",
                        "decisive_observation": "Tolkien is present.",
                        "phase_execution": "correct_non_intervention",
                    }
                ],
                "assessment": "One reviewed negative.",
            }
        ],
    }


def _rollout_record() -> dict[str, object]:
    messages = [
        {"role": "system", "content": "You are a search agent."},
        {"role": "user", "content": "Who wrote The Hobbit?"},
        {
            "role": "assistant",
            "content": (
                '<tool_call>{"name":"search","arguments":'
                '{"query":"The Hobbit author"}}</tool_call>'
            ),
        },
        {"role": "user", "content": "retrieved evidence: Tolkien"},
    ]
    trace = [
        _event(1, 1, "model_input", {"messages": messages[:2]}),
        _event(2, 1, "model_output", {"raw_output": messages[2]["content"]}),
        _event(
            3,
            1,
            "parsed_output",
            {
                "kind": "tool_call",
                "tool_call": {
                    "name": "search",
                    "arguments": {"query": "The Hobbit author"},
                },
            },
        ),
        _event(
            4,
            1,
            "tool_call",
            {"name": "search", "arguments": {"query": "The Hobbit author"}},
        ),
        _event(
            5,
            1,
            "tool_result",
            {
                "name": "search",
                "content": "retrieved evidence: Tolkien",
                "metadata": {},
            },
        ),
        _event(6, 2, "model_input", {"messages": messages}),
        _event(
            7,
            2,
            "model_output",
            {"raw_output": "<final_answer>Tolkien</final_answer>"},
        ),
        _event(
            8,
            2,
            "parsed_output",
            {"kind": "final_answer", "final_answer": "Tolkien"},
        ),
        _event(9, 2, "final_answer_candidate", {"answer": "Tolkien"}),
    ]
    return {
        "example": {
            "example_id": "example-1",
            "question": "Who wrote The Hobbit?",
        },
        "replicate": {"replicate_id": "r000"},
        "run": {
            "question": "Who wrote The Hobbit?",
            "status": "completed",
            "state": {"max_steps": 4},
            "trace": trace,
        },
    }


def _event(
    index: int,
    step: int,
    event_type: str,
    payload: object,
) -> dict[str, object]:
    return {
        "index": index,
        "step": step,
        "event_type": event_type,
        "payload": payload,
    }


if __name__ == "__main__":
    unittest.main()
