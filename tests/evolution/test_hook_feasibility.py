"""Hook-model feasibility probe tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from search_harness.evolution.research.hook_feasibility import (
    HookFeasibilityProbeConfig,
    HookFeasibilityProbeExecutor,
    mechanism_requires_hook_feasibility,
    probe_total_tokens,
    render_hook_feasibility_review_input,
)
from search_harness.evolution.control.domain import (
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
)
from search_harness.evolution.control.transitions import transition_completed
from search_harness.evolution.research.roles.contracts import (
    MechanismSpec,
    TrialReview,
)
from search_harness.framework import HookModelRequest, HookModelResponse


class _ScriptedBackend:
    def __init__(self) -> None:
        self.requests: list[HookModelRequest] = []

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        self.requests.append(request)
        return HookModelResponse(
            raw_output="negative",
            metadata={"usage": {"total_tokens": 10}},
        )


class HookFeasibilityProbeTest(unittest.TestCase):
    def test_probes_real_prefix_without_resuming_student(self) -> None:
        backend = _ScriptedBackend()
        with TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            rollout_file = root / "rollouts.jsonl"
            rollout_file.write_text(
                json.dumps(_rollout_record(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            trial_dir = root / "trial_001"
            trial_dir.mkdir()
            trial_path = trial_dir / "trial.json"
            trial_path.write_text(
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
            review = TrialReview.model_validate(
                {
                    "trial_ref": "trial_001",
                    "predicate_observations": [
                        {
                            "phase": "pre_final",
                            "predicate_label": "negative",
                            "decisive_observation": (
                                "The retrieved evidence names Tolkien."
                            ),
                            "phase_execution": "correct_non_intervention",
                        }
                    ],
                    "assessment": "A reviewed negative control.",
                }
            )

            probe = HookFeasibilityProbeExecutor(
                backend=backend,
                config=HookFeasibilityProbeConfig(
                    max_cases_per_phase=3,
                    repetitions=2,
                    thinking_modes=("enabled", "disabled"),
                ),
            ).run(
                mechanism=_mechanism("hook_model"),
                trial_paths=[trial_path],
                trial_reviews=[review],
                rollout_file=rollout_file,
            )

        phase_probe = probe["phase_probes"][0]
        self.assertEqual(len(backend.requests), 4)
        self.assertEqual(
            [request.thinking_mode for request in backend.requests],
            ["enabled", "enabled", "disabled", "disabled"],
        )
        self.assertEqual(
            phase_probe["case_references"][0]["expected_label"],
            "negative",
        )
        request_text = backend.requests[0].model_input.messages[-1].content
        self.assertIn("retrieved evidence: Tolkien", request_text)
        self.assertNotIn("expected_label", request_text)
        self.assertEqual(probe_total_tokens(probe), 40)

    def test_only_hook_model_mechanisms_require_probe(self) -> None:
        self.assertTrue(
            mechanism_requires_hook_feasibility(_mechanism("hook_model"))
        )
        self.assertFalse(
            mechanism_requires_hook_feasibility(_mechanism("deterministic"))
        )

    def test_reviewer_view_keeps_full_input_once_and_limits_reasoning(self) -> None:
        mechanism = _mechanism("hook_model").model_dump(mode="json")
        probe = {
            "phase_probes": [
                {
                    "phase": "pre_final",
                    "decision_contract": mechanism["phase_rules"][0][
                        "decision_contract"
                    ],
                    "decision_inputs": ["question", "retrieved evidence"],
                    "runtime_inputs": ["task", "conversation"],
                    "case_references": [
                        {
                            "case_id": "trial_001_pre_final",
                            "trial_ref": "trial_001",
                            "expected_label": "positive",
                            "phase_execution": "executed",
                            "decisive_observation": "Evidence is missing.",
                        }
                    ],
                    "experiment": {
                        "system_prompt": "classify",
                        "cases": [
                            {
                                "case_id": "trial_001_pre_final",
                                "user_prompt": "UNIQUE_REAL_PREFIX_INPUT",
                            }
                        ],
                        "observations": [
                            {
                                "case_id": "trial_001_pre_final",
                                "thinking_mode": "enabled",
                                "repetition": 1,
                                "raw_output": "positive",
                                "metadata": {"reasoning": "matched reasoning"},
                                "usage": {"total_tokens": 10},
                            },
                            {
                                "case_id": "trial_001_pre_final",
                                "thinking_mode": "disabled",
                                "repetition": 1,
                                "raw_output": "negative",
                                "metadata": {"reasoning": "x" * 5000},
                                "usage": {"total_tokens": 4},
                            },
                        ],
                    },
                }
            ]
        }

        rendered = render_hook_feasibility_review_input(
            {
                "mechanism": mechanism,
                "probe_evidence": probe,
                "prior_model_experiments": [],
            }
        )
        view = json.loads(rendered)

        self.assertEqual(rendered.count("UNIQUE_REAL_PREFIX_INPUT"), 1)
        observations = view["real_prefix_probes"][0]["cases"][0][
            "observations"
        ]
        self.assertNotIn("reasoning_excerpt", observations[0])
        self.assertIn("reasoning_excerpt", observations[1])
        self.assertLessEqual(len(observations[1]["reasoning_excerpt"]), 1200)


class HookFeasibilityTransitionTest(unittest.TestCase):
    def test_hook_mechanism_routes_through_feasibility_before_compiler(self) -> None:
        distill = WorkItem(
            work_id="distill",
            kind=WorkKind.DISTILL_MECHANISM,
            subject_ref="generation:1:harness_v0001",
            input_refs={"trial_001": "trial.json"},
        )

        plan = transition_completed(
            item=distill,
            result=EffectResult(
                outcome={
                    "output": {
                        "decision": "distilled",
                        "mechanism_ref": "mechanism_001",
                        "rationale": "supported",
                        "next_obligation": None,
                    },
                    "requires_hook_feasibility": True,
                },
                artifact_refs={"mechanism_file": "mechanism.json"},
            ),
            config=EvolutionControlConfig(),
        )

        self.assertEqual(
            plan.next_items[0].kind,
            WorkKind.VERIFY_HOOK_FEASIBILITY,
        )

    def test_supported_probe_hands_guidance_to_compiler(self) -> None:
        work = WorkItem(
            work_id="feasibility",
            kind=WorkKind.VERIFY_HOOK_FEASIBILITY,
            subject_ref="generation:1:harness_v0001",
            payload={"implementation_constraints": ["preserve fallback"]},
        )

        plan = transition_completed(
            item=work,
            result=EffectResult(
                outcome={
                    "output": {
                        "decision": "feasible",
                        "phase_findings": [],
                        "assessment": "supported",
                        "compiler_guidance": [
                            "Use disabled thinking and parse the leading label."
                        ],
                        "revision_feedback": None,
                    }
                },
                artifact_refs={
                    "hook_feasibility_artifact": "feasibility.json"
                },
            ),
            config=EvolutionControlConfig(),
        )

        next_work = plan.next_items[0]
        self.assertEqual(next_work.kind, WorkKind.COMPILE_CANDIDATE)
        self.assertEqual(
            next_work.payload["implementation_constraints"],
            [
                "preserve fallback",
                "Use disabled thinking and parse the leading label.",
            ],
        )

    def test_model_boundary_failure_returns_to_researcher(self) -> None:
        work = WorkItem(
            work_id="feasibility",
            kind=WorkKind.VERIFY_HOOK_FEASIBILITY,
            subject_ref="generation:1:harness_v0001",
        )
        output = {
            "decision": "needs_research_revision",
            "phase_findings": [],
            "assessment": "positive and negative states overlap",
            "compiler_guidance": [],
            "revision_feedback": "Narrow the semantic boundary.",
        }

        plan = transition_completed(
            item=work,
            result=EffectResult(outcome={"output": output}),
            config=EvolutionControlConfig(),
        )

        next_work = plan.next_items[0]
        self.assertEqual(next_work.kind, WorkKind.RESEARCH_HYPOTHESIS)
        self.assertEqual(
            next_work.payload["research_continuation"]["feedback_source"],
            "hook_feasibility_reviewer",
        )


def _mechanism(evaluator: str) -> MechanismSpec:
    return MechanismSpec.model_validate(
        {
            "goal": "Preserve answers supported by visible evidence.",
            "phase_rules": [
                {
                    "phase": "pre_final",
                    "guards": [],
                    "decision_contract": {
                        "predicate": "Is the answer unsupported?",
                        "positive_rule": "Evidence does not support the answer.",
                        "negative_rule": "Evidence directly supports the answer.",
                        "uncertain_rule": "Evidence cannot be inspected.",
                        "output_labels": [
                            "positive",
                            "negative",
                            "uncertain",
                        ],
                        "evidence_coverage": {
                            "positive": ["unsupported answer"],
                            "negative": ["supported answer"],
                            "uncertain": [],
                        },
                    },
                    "decision_inputs": ["question", "retrieved evidence"],
                    "runtime_inputs": ["task", "conversation"],
                    "decision_evaluator": evaluator,
                    "action": "Defer the final answer once.",
                    "fallback": {
                        "negative": "Continue unchanged.",
                        "uncertain": "Continue unchanged.",
                        "budget_exhausted": "Continue unchanged.",
                    },
                    "activation_budget": 1,
                }
            ],
            "behavioral_pseudocode": "At pre_final, classify and defer once.",
            "state_scope": "One rollout-local consumed flag.",
            "expected_behavior": "A positive state is deferred once.",
            "evidence_refs": ["trial_001"],
        }
    )


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
            "answer": "Tolkien",
            "metadata": {},
        },
        "replicate": {"replicate_id": "r000"},
        "run": {
            "question": "Who wrote The Hobbit?",
            "answer": "Tolkien",
            "status": "completed",
            "error": None,
            "state": {
                "question": "Who wrote The Hobbit?",
                "max_steps": 4,
            },
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
