from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.teacher._intervention import (
    InterventionRunner,
    InterventionRuntimeConfig,
)
from search_harness.teacher._intervention.runtime import _phase_effects
from search_harness.core import HookPhase, ModelInput

from tests.teacher.test_intervention_prefix import _write_rollout


@dataclass
class SequenceModel:
    outputs: list[str]

    def __post_init__(self) -> None:
        self.inputs: list[ModelInput] = []

    def generate(self, model_input: ModelInput) -> str:
        self.inputs.append(model_input)
        if not self.outputs:
            raise AssertionError("model received more calls than expected")
        return self.outputs.pop(0)


class JudgeModel(SequenceModel):
    def get_last_generation_metadata(self) -> dict[str, object]:
        return {"usage": {"total_tokens": 10}}


class InterventionRuntimeTest(TestCase):
    def test_teacher_judge_resolves_inconclusive_branch_without_exposing_golden(self) -> None:
        """验证语义正确的非精确答案由独立 Judge 解析为 1。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            plugins_root = _make_plugins(root)
            student = SequenceModel(
                outputs=["<final_answer>The author was J. R. R. Tolkien.</final_answer>"]
            )
            teacher = SequenceModel(
                outputs=[
                    '<tool_call>{"name":"continue_without_change","arguments":{'
                    '"reason":"Retained evidence is sufficient."}}</tool_call>',
                    "<final_answer>The intervention preserved the supported answer.</final_answer>",
                ]
            )
            runner = InterventionRunner(
                InterventionRuntimeConfig(
                    env_file=root / ".env",
                    plugins_root=plugins_root,
                    output_root=root / "intervention-runs",
                    actor_max_steps=4,
                    worker_max_steps_per_activation=4,
                    teacher_judge=True,
                ),
                student_model=student,
                teacher_model=teacher,
                judge_model=JudgeModel(['{"score":1}']),
            )

            artifact = runner.run(
                rollout_file=rollout_file,
                example_id="example-1",
                replicate_id="r000",
                fork_step=1,
                fork_phase=HookPhase.POST_TOOL,
                intent="Test semantic evaluation.",
                hook_guidance={HookPhase.POST_TOOL: "Preserve supported evidence."},
            )

        branch = artifact["comparison"]["branch"]
        self.assertEqual(branch["score"], 1)
        self.assertEqual(branch["score_source"], "teacher")
        self.assertNotIn("golden", json.dumps(branch).casefold())

    def test_runs_worker_at_source_boundary_and_continues_student(self) -> None:
        """验证教师在源 post_tool 边界注入指导后学生从该 prefix 继续。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            plugins_root = _make_plugins(root)
            student = SequenceModel(
                outputs=["<final_answer>J. R. R. Tolkien</final_answer>"]
            )
            teacher = SequenceModel(
                outputs=[
                    '<tool_call>{"name":"inspect_actor_context","arguments":{}}</tool_call>',
                    '<tool_call>{"name":"replace_model_input","arguments":'
                    '{"system_instruction":"Use retrieved evidence and verify every '
                    'required relation.","user_instruction":"Use the retrieved '
                    'evidence before answering."}}</tool_call>',
                    "<final_answer>The guidance worked because the branch used the retained evidence.</final_answer>",
                ]
            )
            runner = _runner(root, plugins_root, student, teacher)

            artifact = runner.run(
                rollout_file=rollout_file,
                example_id="example-1",
                replicate_id="r000",
                fork_step=1,
                fork_phase=HookPhase.POST_TOOL,
                intent="Test explicit evidence-use guidance.",
                hook_guidance={
                    HookPhase.POST_TOOL: "Inspect the result and guide evidence use."
                },
            )

            persisted = json.loads(
                Path(artifact["artifact_file"]).read_text(encoding="utf-8")
            )

        student_messages = student.inputs[0].messages
        self.assertEqual(student_messages[-2].content, "retrieved evidence: Tolkien")
        self.assertEqual(
            student_messages[-1].content,
            "Use the retrieved evidence before answering.",
        )
        self.assertEqual(
            student_messages[0].content,
            "Use retrieved evidence and verify every required relation.",
        )
        self.assertEqual(artifact["comparison"]["exact_match_delta"], 1)
        self.assertEqual(artifact["branch_run"]["answer"], "J. R. R. Tolkien")
        self.assertEqual(len(artifact["intervention_changes"]), 1)
        self.assertNotIn("worker_summary", persisted)
        self.assertNotIn("worker_summary", artifact)
        inspected = teacher.inputs[1].messages[-1].content
        self.assertIn('"event_type": "hook_applied"', inspected)
        worker_activation_prompt = teacher.inputs[0].messages[-1].content
        self.assertIn("system_instruction", worker_activation_prompt)
        self.assertNotIn("messages_json", worker_activation_prompt)
        self.assertNotIn("value_json", worker_activation_prompt)
        self.assertNotIn("defer_final_answer", worker_activation_prompt)
        self.assertNotIn("accept_final_answer", worker_activation_prompt)

    def test_worker_can_defer_pre_final_through_specific_action_tool(self) -> None:
        """验证 Worker 无需嵌套 JSON 即可修改 final_decision。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            plugins_root = _make_plugins(root)
            student = SequenceModel(
                outputs=[
                    "<final_answer>Shakespeare</final_answer>",
                    "<final_answer>J. R. R. Tolkien</final_answer>",
                ]
            )
            teacher = SequenceModel(
                outputs=[
                    '<tool_call>{"name":"defer_final_answer","arguments":'
                    '{"feedback":"","reason":"Incomplete first attempt."}}</tool_call>',
                    '<tool_call>{"name":"defer_final_answer","arguments":'
                    '{"feedback":"Recheck the retrieved evidence.",'
                    '"reason":"The candidate conflicts with the evidence."}}</tool_call>',
                    '<tool_call>{"name":"continue_without_change","arguments":'
                    '{"reason":"The revised answer now follows the evidence."}}</tool_call>',
                    "<final_answer>Deferring the first unsupported answer corrected the branch.</final_answer>",
                ]
            )
            runner = _runner(root, plugins_root, student, teacher)

            artifact = runner.run(
                rollout_file=rollout_file,
                example_id="example-1",
                replicate_id="r000",
                fork_step=1,
                fork_phase=HookPhase.POST_TOOL,
                intent="Test final-answer verification.",
                hook_guidance={
                    HookPhase.PRE_FINAL: "Defer a candidate that conflicts with evidence."
                },
            )

        self.assertEqual(artifact["branch_run"]["answer"], "J. R. R. Tolkien")
        self.assertEqual(len(artifact["intervention_changes"]), 2)
        second_student_input = student.inputs[1].to_dict()["messages"]
        self.assertEqual(second_student_input[-1]["content"], "Recheck the retrieved evidence.")
        tool_errors = [
            event
            for event in artifact["worker_trace"]
            if event["event_type"] == "worker_tool_result"
            and event["tool_result"]["content"].startswith("TOOL_INPUT_ERROR")
        ]
        self.assertEqual(len(tool_errors), 1)

    def test_same_worker_transcript_controls_multiple_hook_phases(self) -> None:
        """验证同一 Worker 会话在一个分支内连续处理 post_tool 与 pre_final。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            plugins_root = _make_plugins(root)
            student = SequenceModel(
                outputs=[
                    "<final_answer>Shakespeare</final_answer>",
                    "<final_answer>J. R. R. Tolkien</final_answer>",
                ]
            )
            teacher = SequenceModel(
                outputs=[
                    '<tool_call>{"name":"append_context_message","arguments":'
                    '{"role":"user","content":"Track the still unsupported '
                    'relation before finalizing.","persistence":'
                    '"next_generation"}}</tool_call>',
                    '<tool_call>{"name":"defer_final_answer","arguments":'
                    '{"feedback":"Resolve the evidence gap before answering.",'
                    '"reason":"The first candidate is not fully supported."}}'
                    "</tool_call>",
                    "<final_answer>The two-phase intervention caused a "
                    "supported revision.</final_answer>",
                ]
            )
            runner = _runner(root, plugins_root, student, teacher)

            artifact = runner.run(
                rollout_file=rollout_file,
                example_id="example-1",
                replicate_id="r000",
                fork_step=1,
                fork_phase=HookPhase.POST_TOOL,
                intent="Test one causal post-tool to pre-final plan.",
                hook_guidance={
                    HookPhase.POST_TOOL: (
                        "Mark the visible relation that still lacks support."
                    ),
                    HookPhase.PRE_FINAL: (
                        "Defer a candidate while that relation is unsupported."
                    ),
                },
                activation_budgets={
                    HookPhase.POST_TOOL: 1,
                    HookPhase.PRE_FINAL: 1,
                },
            )

        self.assertEqual(
            artifact["activation_counts"],
            {HookPhase.POST_TOOL: 1, HookPhase.PRE_FINAL: 1},
        )
        self.assertEqual(
            [
                change["phase"]
                for change in artifact["intervention_changes"]
            ],
            [HookPhase.POST_TOOL, HookPhase.PRE_FINAL],
        )
        activations = [
            event
            for event in artifact["worker_trace"]
            if event["event_type"] == "worker_activation"
        ]
        self.assertEqual(
            [event["phase"] for event in activations],
            [HookPhase.POST_TOOL, HookPhase.PRE_FINAL],
        )
        second_activation_input = "\n".join(
            message.content for message in teacher.inputs[1].messages
        )
        self.assertIn("phase=post_tool", second_activation_input)
        self.assertIn("phase=pre_final", second_activation_input)
        self.assertNotIn(
            "defer_final_answer",
            teacher.inputs[0].messages[-1].content,
        )
        self.assertIn(
            "defer_final_answer",
            teacher.inputs[1].messages[-1].content,
        )
        self.assertEqual(
            artifact["branch_run"]["answer"],
            "J. R. R. Tolkien",
        )
        self.assertEqual(
            [
                {
                    "phase": effect["phase"],
                    "anchor_found": effect["anchor_found"],
                    "next_model_decision": effect["next_model_decision"],
                    "tool_calls_before_next_final": (
                        effect["tool_calls_before_next_final"]
                    ),
                }
                for effect in artifact["phase_effects"]
            ],
            [
                {
                    "phase": HookPhase.POST_TOOL,
                    "anchor_found": True,
                    "next_model_decision": {
                        "step": 1,
                        "kind": "final_answer",
                        "tool_name": None,
                    },
                    "tool_calls_before_next_final": 0,
                },
                {
                    "phase": HookPhase.PRE_FINAL,
                    "anchor_found": True,
                    "next_model_decision": {
                        "step": 2,
                        "kind": "final_answer",
                        "tool_name": None,
                    },
                    "tool_calls_before_next_final": 0,
                },
            ],
        )

    def test_phase_effects_align_repeated_phase_activations_by_step(self) -> None:
        """验证同一 phase 多次激活时分别归因到各自后续决策。"""

        changes = [
            {
                "scope": "branch",
                "phase": HookPhase.POST_TOOL,
                "step": 1,
                "phase_activation": 1,
                "action": {"kind": "append_context_message"},
            },
            {
                "scope": "branch",
                "phase": HookPhase.POST_TOOL,
                "step": 2,
                "phase_activation": 2,
                "action": {"kind": "append_context_message"},
            },
        ]
        trace = [
            _hook_event(index=1, step=1, phase=HookPhase.POST_TOOL),
            _parsed_event(index=2, step=2, kind="tool_call", tool="search"),
            {
                "index": 3,
                "step": 2,
                "event_type": "tool_call",
                "payload": {"name": "search", "arguments": {}},
            },
            _hook_event(index=4, step=2, phase=HookPhase.POST_TOOL),
            _parsed_event(index=5, step=3, kind="final_answer"),
            {
                "index": 6,
                "step": 3,
                "event_type": "final_answer",
                "payload": {"answer": "done"},
            },
        ]

        effects = _phase_effects(changes, trace)

        self.assertEqual(
            [effect["next_model_decision"]["kind"] for effect in effects],
            ["tool_call", "final_answer"],
        )
        self.assertEqual(
            [effect["tool_calls_before_next_final"] for effect in effects],
            [1, 0],
        )
        self.assertTrue(all(effect["anchor_found"] for effect in effects))

    def test_phase_effects_do_not_guess_when_hook_anchor_is_missing(self) -> None:
        """验证缺失 Hook 锚点时不会把轨迹开头误归因为 phase 效果。"""

        effects = _phase_effects(
            [
                {
                    "scope": "branch",
                    "phase": HookPhase.PRE_FINAL,
                    "step": 9,
                    "phase_activation": 1,
                    "action": {"kind": "replace_stage_value"},
                }
            ],
            [_parsed_event(index=1, step=1, kind="tool_call", tool="search")],
        )

        self.assertFalse(effects[0]["anchor_found"])
        self.assertIsNone(effects[0]["next_model_decision"])
        self.assertEqual(effects[0]["tool_calls_before_next_final"], 0)

def _runner(
    root: Path,
    plugins_root: Path,
    student: SequenceModel,
    teacher: SequenceModel,
) -> InterventionRunner:
    return InterventionRunner(
        InterventionRuntimeConfig(
            env_file=root / ".env",
            plugins_root=plugins_root,
            output_root=root / "intervention-runs",
            actor_max_steps=4,
            worker_max_steps_per_activation=4,
        ),
        student_model=student,
        teacher_model=teacher,
    )


def _hook_event(*, index: int, step: int, phase: str) -> dict[str, object]:
    return {
        "index": index,
        "step": step,
        "event_type": "hook_applied",
        "payload": {
            "phase": phase,
            "hook_id": "intervention_worker_bridge",
            "changes": [],
        },
    }


def _parsed_event(
    *,
    index: int,
    step: int,
    kind: str,
    tool: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"kind": kind}
    if tool is not None:
        payload["tool_call"] = {"name": tool, "arguments": {}}
    return {
        "index": index,
        "step": step,
        "event_type": "parsed_output",
        "payload": payload,
    }


def _make_plugins(root: Path) -> Path:
    plugins_root = root / "plugins"
    prompt_dir = plugins_root / "prompts" / "test"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "plugin.py").write_text(
        '''from search_harness.core import ChatMessage, ModelInput

class Prompt:
    def build(self, state):
        return ModelInput.from_messages([
            ChatMessage(role="system", content="unused after prefix reconstruction"),
            ChatMessage(role="user", content=state.question),
            *state.conversation_messages,
        ])

def build(config, context, tools):
    return Prompt()
''',
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "harness_id": "intervention_test",
        "tools": [],
        "prompt": {
            "instance_id": "test_prompt",
            "entrypoint": "prompts/test/plugin.py:build",
            "config": {},
            "evolution_policy": "fixed",
        },
        "extensions": [],
    }
    (plugins_root / "harness.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return plugins_root
