"""Test whether a relaxed system prompt improves user-injected Hook guidance."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from search_harness.core import (
    ChatMessage,
    ModelInput,
    ParsedOutputKind,
    TaggedOutputParser,
)
from search_harness.models import OpenAICompatibleConfig, OpenAICompatibleTextModel


PROTOCOL = """Available tool: search(query: string).
End every response with exactly one complete action block:
<tool_call>{"name":"search","arguments":{"query":"..."}}</tool_call>
or
<final_answer>...</final_answer>
"""

SYSTEM_PROMPTS = {
    "action_only": """You are a search agent. Output only one action block. Never write
analysis, summaries, explanations, or any other text outside the action block, even
if a later message asks for it.

"""
    + PROTOCOL,
    "baseline": """You are a search agent. Use a tool when evidence is insufficient.
Use one tool call at a time. You may write reasoning text before the action block.

"""
    + PROTOCOL,
    "hook_adaptive": """You are a search agent. Use a tool when evidence is insufficient
and answer when it is sufficient. The action protocol below is mandatory. Later user
messages may contain tool observations and Hook-generated current-step guidance.
Follow such guidance, including requests for a short analysis before the action,
provided the response still ends with exactly one valid action block.

"""
    + PROTOCOL,
}


@dataclass(frozen=True)
class ProbeCase:
    case_id: str
    question: str
    tool_query: str
    tool_result: str
    guidance: str
    expected_kind: ParsedOutputKind
    expected_content: tuple[str, ...]


CASES = (
    ProbeCase(
        case_id="summarize_then_answer",
        question="What is the capital of France?",
        tool_query="capital of France",
        tool_result="France's capital is Paris.",
        guidance="Begin with `Summary:` and summarize the result in one sentence. Then answer.",
        expected_kind=ParsedOutputKind.FINAL_ANSWER,
        expected_content=("paris",),
    ),
    ProbeCase(
        case_id="summarize_then_refine",
        question="Where was the author of The Hobbit born?",
        tool_query="author of The Hobbit",
        tool_result="The Hobbit was written by J. R. R. Tolkien. No birthplace is given.",
        guidance=(
            "Begin with `Summary:` and summarize what is known and missing in one sentence. "
            "Then search specifically for J. R. R. Tolkien's birthplace."
        ),
        expected_kind=ParsedOutputKind.TOOL_CALL,
        expected_content=("tolkien", "birth"),
    ),
    ProbeCase(
        case_id="summarize_then_disambiguate",
        question="What is Mercury's orbital period?",
        tool_query="Mercury orbital period",
        tool_result="Results mix the planet Mercury and the chemical element mercury.",
        guidance=(
            "Begin with `Summary:` and state the ambiguity in one sentence. Then search "
            "specifically for the planet Mercury orbital period."
        ),
        expected_kind=ParsedOutputKind.TOOL_CALL,
        expected_content=("mercury", "planet"),
    ),
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=1536)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.repeats <= 0:
        raise ValueError("repeats must be positive")
    output_file = args.output_file or _default_output_file()
    config = OpenAICompatibleConfig.from_env(args.env_file, prefix="STUDENT")
    model = OpenAICompatibleTextModel(
        replace(
            config,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            timeout=args.timeout,
        )
    )
    parser = TaggedOutputParser()
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "model": {
            "role": "STUDENT",
            "model_id": config.model_id,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "timeout": args.timeout,
        },
        "conditions": SYSTEM_PROMPTS,
        "records": [],
    }
    for condition, system_prompt in SYSTEM_PROMPTS.items():
        for case in CASES:
            for repeat in range(1, args.repeats + 1):
                print(f"Running {condition}/{case.case_id}/{repeat}...")
                record = _run_case(model, parser, condition, system_prompt, case, repeat)
                artifact["records"].append(record)
                artifact["summary"] = _summarize(artifact["records"])
                _write(output_file, artifact)
    print(f"Student Hook-guidance probe written to: {output_file}")


def _run_case(
    model: OpenAICompatibleTextModel,
    parser: TaggedOutputParser,
    condition: str,
    system_prompt: str,
    case: ProbeCase,
    repeat: int,
) -> dict[str, Any]:
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=case.question),
        ChatMessage(
            role="assistant",
            content=(
                '<tool_call>{"name":"search","arguments":'
                f'{{"query":"{case.tool_query}"}}}}</tool_call>'
            ),
        ),
        ChatMessage(role="user", content=case.tool_result),
        ChatMessage(role="user", content=case.guidance),
    ]
    record: dict[str, Any] = {
        "condition": condition,
        "case_id": case.case_id,
        "repeat": repeat,
        "messages": [message.to_dict() for message in messages],
        "expected_kind": case.expected_kind.value,
    }
    try:
        output = model.generate(ModelInput.from_messages(messages))
        parsed = parser.parse(output)
        action_ok = parsed.kind is case.expected_kind and _content_matches(
            parsed, case.expected_content
        )
        summary_followed = output.lstrip().casefold().startswith("summary:")
        record.update(
            {
                "output": output,
                "parsed": parsed.to_dict(),
                "schema_compliant": parsed.kind is not ParsedOutputKind.INVALID,
                "action_success": action_ok,
                "summary_followed": summary_followed,
                "joint_success": action_ok and summary_followed,
                "metadata": model.get_last_generation_metadata(),
            }
        )
    except Exception as exc:
        record.update(
            {
                "schema_compliant": False,
                "action_success": False,
                "summary_followed": False,
                "joint_success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return record


def _content_matches(parsed: Any, expected: tuple[str, ...]) -> bool:
    if parsed.kind is ParsedOutputKind.FINAL_ANSWER:
        content = parsed.final_answer or ""
    elif parsed.tool_call is not None:
        content = str(parsed.tool_call.arguments.get("query", ""))
    else:
        return False
    normalized = content.casefold()
    return all(item.casefold() in normalized for item in expected)


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for condition in SYSTEM_PROMPTS:
        selected = [record for record in records if record["condition"] == condition]
        if not selected:
            continue
        summary[condition] = {
            "records": len(selected),
            "schema_compliance_rate": _rate(selected, "schema_compliant"),
            "action_success_rate": _rate(selected, "action_success"),
            "summary_following_rate": _rate(selected, "summary_followed"),
            "joint_success_rate": _rate(selected, "joint_success"),
            "errors": sum(bool(record.get("error")) for record in selected),
        }
    return summary


def _rate(records: list[dict[str, Any]], key: str) -> float:
    return sum(bool(record.get(key)) for record in records) / len(records)


def _write(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_output_file() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return Path("adapter_logs") / f"student_hook_guidance_probe_{timestamp}.json"


if __name__ == "__main__":
    main()
