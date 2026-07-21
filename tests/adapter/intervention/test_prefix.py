from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.adapter.intervention import (
    PrefixSelector,
    build_prefix_timeline,
    load_reconstructed_prefix,
    load_rollout_record,
    resolve_prefix_boundary,
    summarize_rollout_example,
)
from search_harness.core import HookPhase, ToolResult


class InterventionPrefixTest(TestCase):
    def test_example_summary_and_trajectory_use_two_level_identity(self) -> None:
        """验证 example_id 返回目录，而复合键精确定位一条重复轨迹。"""

        first = _rollout_record()
        second = _rollout_record()
        first["replicate"] = {
            "replicate_id": "r000",
            "index": 0,
            "sampling_seed": 42,
        }
        second["replicate"] = {
            "replicate_id": "r001",
            "index": 1,
            "sampling_seed": 43,
        }
        second["run"]["answer"] = "J. R. R. Tolkien"
        with TemporaryDirectory() as tmpdir:
            rollout_file = Path(tmpdir) / "rollout.jsonl"
            rollout_file.write_text(
                json.dumps(first) + "\n" + json.dumps(second) + "\n",
                encoding="utf-8",
            )

            summary = summarize_rollout_example(rollout_file, "example-1")
            selected = load_rollout_record(
                rollout_file, "example-1", "r001"
            )

        self.assertEqual(
            [item["replicate_id"] for item in summary["replicates"]],
            ["r000", "r001"],
        )
        self.assertEqual(selected["run"]["answer"], "J. R. R. Tolkien")

    def test_builds_ordered_selectable_prefix_timeline(self) -> None:
        """验证轨迹目录仅编号实际可重建边界并可反解精确事件坐标。"""

        with TemporaryDirectory() as tmpdir:
            rollout_file = Path(tmpdir) / "rollout.jsonl"
            _write_rollout(rollout_file)
            record = load_rollout_record(rollout_file, "example-1", "r000")

            timeline = build_prefix_timeline(record)
            boundary = resolve_prefix_boundary(record, 5)

        self.assertEqual(
            [item["prefix_id"] for item in timeline],
            list(range(1, len(timeline) + 1)),
        )
        self.assertEqual(
            boundary,
            {
                "prefix_id": 5,
                "step": 1,
                "phase": "post_tool",
                "event_index": 6,
                "state_summary": (
                    "Tool result available to the continuation: "
                    "retrieved evidence: Tolkien"
                ),
            },
        )

    def test_post_tool_boundary_keeps_result_in_model_context(self) -> None:
        """验证 post_tool 语义边界保留工具结果但不暴露审计事件。"""

        with TemporaryDirectory() as tmpdir:
            rollout_file = Path(tmpdir) / "rollout.jsonl"
            _write_rollout(rollout_file)

            prefix = load_reconstructed_prefix(
                PrefixSelector(
                    rollout_file=rollout_file,
                    example_id="example-1",
                    replicate_id="r000",
                    step=1,
                    phase=HookPhase.POST_TOOL,
                )
            )

        messages = prefix.model_input.messages
        self.assertEqual(
            [message.role for message in messages],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(messages[-1].content, "retrieved evidence: Tolkien")
        self.assertNotIn("hook_applied", json.dumps(prefix.model_input.to_dict()))
        self.assertEqual(prefix.retained_trace[-1]["event_type"], "tool_result")
        self.assertIsInstance(prefix.stage_values["tool_result"], ToolResult)


def _write_rollout(path: Path) -> None:
    record = _rollout_record()
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")


def _rollout_record() -> dict[str, object]:
    first_input = {
        "messages": [
            {"role": "system", "content": "You are a test search agent."},
            {"role": "user", "content": "Who wrote The Hobbit?"},
        ]
    }
    tool_output = (
        '<tool_call>{"name":"search","arguments":{"query":"The Hobbit author"}}'
        "</tool_call>"
    )
    tool_call = {"name": "search", "arguments": {"query": "The Hobbit author"}}
    second_input = {
        "messages": [
            *first_input["messages"],
            {"role": "assistant", "content": tool_output},
            {"role": "user", "content": "retrieved evidence: Tolkien"},
        ]
    }
    trace = [
        _event(1, 1, "model_input", first_input),
        _event(2, 1, "model_output", {"raw_output": tool_output}),
        _event(3, 1, "parsed_output", {"kind": "tool_call", "tool_call": tool_call}),
        _event(4, 1, "tool_call", tool_call),
        _event(
            5,
            1,
            "hook_applied",
            {"phase": "post_tool", "hook_id": "audit", "changes": []},
        ),
        _event(
            6,
            1,
            "tool_result",
            {"name": "search", "content": "retrieved evidence: Tolkien", "metadata": {}},
        ),
        _event(7, 2, "model_input", second_input),
        _event(8, 2, "model_output", {"raw_output": "<final_answer>Shakespeare</final_answer>"}),
        _event(
            9,
            2,
            "parsed_output",
            {"kind": "final_answer", "final_answer": "Shakespeare"},
        ),
        _event(10, 2, "final_answer_candidate", {"answer": "Shakespeare"}),
        _event(11, 2, "final_answer", {"answer": "Shakespeare"}),
    ]
    return {
        "example": {
            "example_id": "example-1",
            "question": "Who wrote The Hobbit?",
            "answer": "J. R. R. Tolkien",
            "metadata": {},
        },
        "run": {
            "question": "Who wrote The Hobbit?",
            "answer": "Shakespeare",
            "status": "completed",
            "error": None,
            "state": {
                "question": "Who wrote The Hobbit?",
                "max_steps": 4,
                "step": 2,
                "status": "completed",
                "final_answer": "Shakespeare",
                "error": None,
                "model_inputs": [first_input, second_input],
                "model_outputs": [tool_output, "<final_answer>Shakespeare</final_answer>"],
                "parsed_outputs": [],
                "tool_interactions": [
                    {
                        "tool_call": tool_call,
                        "tool_result": {
                            "name": "search",
                            "content": "retrieved evidence: Tolkien",
                            "metadata": {},
                        },
                    }
                ],
                "conversation_messages": [
                    {"role": "assistant", "content": tool_output},
                    {"role": "user", "content": "retrieved evidence: Tolkien"},
                ],
                "hook_state": {},
            },
            "trace": trace,
        },
    }


def _event(index: int, step: int, event_type: str, payload: object) -> dict[str, object]:
    return {
        "index": index,
        "step": step,
        "event_type": event_type,
        "payload": payload,
    }
