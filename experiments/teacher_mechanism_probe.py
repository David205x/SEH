"""Probe how a Teacher discovers Harness intervention mechanisms."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from search_harness.framework import ChatMessage, ModelInput
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
)


SYSTEM = """You are a senior research architect studying an evolvable agent Harness.
Reason from the evidence and constraints given in each experiment. Do not assume
unlisted framework capabilities. Distinguish deterministic transformations from
semantic decisions, and account for accuracy, token cost, auditability, and
causal attribution. Return a concise but technically specific design analysis.
"""

CURRENT_EVIDENCE = """Observed candidate review:
- The parent scored 60 correct out of 100 records; the candidate scored 64.
- Paired review found 10 candidate-only-correct, 9 parent-only-correct, and 4
  transitions involving unresolved parent judgments.
- Mean tool calls rose from 1.08 to 1.19 and total Student tokens rose about 20.6%.
- The only patch replaced a short post-tool reminder with four static search
  guidelines injected as a user message after every tool result.
- The guidelines increased multi-query behavior but were followed inconsistently.
- Some regressions were over-cautious refusals after incomplete retrieval; some
  errors involved entity/referent confusion that static wording did not resolve.
- The current Critic recommended shorter prompt guidance and entity-disambiguation
  instructions, but did not propose a new inference mechanism.
"""

VISIBLE_HOOKS = """Framework facts visible to the analyst:
- A fixed single-model loop alternates one model generation with at most one tool
  call, then continues until a final answer or step limit.
- Registered Hooks run synchronously at lifecycle phases around prompt building,
  model output, parsing, tool execution, and finalization.
- Hooks can read the complete current rollout projection, keep typed per-rollout
  extension/shared state, and atomically replace permitted current-stage values.
- A post-prompt Hook can replace the complete ModelInput for that generation.
- Core AgentState is not directly writable, tools are fixed for the run, and Hook
  state does not survive across rollouts.
"""

CAPABILITY_SPACE = """Additional intervention capabilities available to evolved components:
- deterministic stateful Hooks and conditional stage transformations;
- dynamic selection, compression, ordering, and injection of model context;
- deterministic normalization of parsed tool calls or tool results;
- one bounded semantic inference call from a Hook through a traced runtime profile;
  the Hook chooses the inference input, parses its output, and explicitly decides
  whether and how the result changes the main loop;
- no nested AgentLoop, no hidden direct network client, and no untraced mutation.
"""

SYNTHETIC_HISTORY = """Synthetic iteration history for this probe (not a claim about completed project runs):
1. A generic post-tool reminder changed behavior weakly and was ignored often.
2. A longer checklist increased retrieval and token cost but produced a nearly
   symmetric improvement/regression trade-off.
3. A shorter high-priority instruction reduced prompt cost but still failed on
   cases where the correct action depended on entity identity and evidence content.
Across attempts, wording changes altered compliance but did not reliably perform
conditional evidence-sufficiency or referent-disambiguation judgments.
"""

COMPILER_AUTONOMY = """Compiler contract:
- Treat proposals as behavioral intent rather than prescribed source code.
- Prefer the smallest auditable intervention that fits mutable Component boundaries.
- It may implement deterministic Hooks, context transformations, or a bounded
  model-assisted Hook. Model-assisted Hooks must declare an allowed profile,
  construct a bounded ModelInput, parse a structured response, and define failure
  behavior. The Compiler must justify added cost and avoid model calls when a
  deterministic transformation is sufficient.
"""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-tokens", type=int, default=2200)
    parser.add_argument("--temperature", type=float, default=0.2)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    output_file = args.output_file or _default_output_file()
    config = OpenAICompatibleConfig.from_env(args.env_file, prefix="TEACHER")
    model = OpenAICompatibleModel(
        replace(
            config,
            timeout=args.timeout,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    )
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "model": {
            "role": "TEACHER",
            "model_id": config.model_id,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "timeout": args.timeout,
        },
        "experiments": [],
    }

    baseline_prompt = CURRENT_EVIDENCE + "\n" + VISIBLE_HOOKS + """

Without assuming any other framework mechanism, propose the next two candidate
interventions. Explain what information each intervention consumes, what it changes,
and why it could escape the current prompt-wording local optimum.
"""
    _run(model, artifact, output_file, "e0_evidence_only_a", baseline_prompt)
    _run(model, artifact, output_file, "e0_evidence_only_b", baseline_prompt)

    _run(
        model,
        artifact,
        output_file,
        "e1_capability_space",
        CURRENT_EVIDENCE
        + "\n"
        + VISIBLE_HOOKS
        + "\n"
        + CAPABILITY_SPACE
        + """

Choose an intervention architecture. Do not select a mechanism merely because it
is available: derive whether the failed behavior is deterministic or semantic,
describe the exact bounded context it should consume, and compare it against a
static prompt or deterministic Hook.
""",
    )

    _run(
        model,
        artifact,
        output_file,
        "e2_failure_history",
        CURRENT_EVIDENCE
        + "\n"
        + VISIBLE_HOOKS
        + "\n"
        + SYNTHETIC_HISTORY
        + """

Infer what mechanism class should be tried next. You have not been told about any
additional runtime primitive, so separate the behavioral requirement you can infer
from the implementation mechanism you cannot assume.
""",
    )

    _run(
        model,
        artifact,
        output_file,
        "e3_compiler_autonomy",
        CURRENT_EVIDENCE
        + "\n"
        + VISIBLE_HOOKS
        + "\n"
        + CAPABILITY_SPACE
        + "\n"
        + COMPILER_AUTONOMY
        + """

Act as the Compiler. The behavioral proposal is: after a retrieval, intervene only
when deciding whether evidence is sufficient or a named referent is ambiguous;
produce compact guidance for the next Student step. Select and specify the mechanism,
its context contract, output schema, state transitions, fallback, and trace evidence.
""",
    )

    combined = _run(
        model,
        artifact,
        output_file,
        "e4_combined_discovery",
        CURRENT_EVIDENCE
        + "\n"
        + VISIBLE_HOOKS
        + "\n"
        + CAPABILITY_SPACE
        + "\n"
        + SYNTHETIC_HISTORY
        + "\n"
        + COMPILER_AUTONOMY
        + """

Design the next atomic candidate. The goal is not to force a model call; choose the
least powerful mechanism that can test the hypothesis. State why prior attempts
failed as a mechanism class, define context and mutation boundaries, and propose a
paired evaluation that could falsify your design.
""",
    )
    if combined is not None:
        _run_dialogue(
            model,
            artifact,
            output_file,
            "e4_adversarial_followup",
            [
                ChatMessage(role="system", content=SYSTEM),
                ChatMessage(
                    role="user",
                    content=CURRENT_EVIDENCE
                    + "\n"
                    + VISIBLE_HOOKS
                    + "\n"
                    + CAPABILITY_SPACE
                    + "\n"
                    + SYNTHETIC_HISTORY
                    + "\n"
                    + COMPILER_AUTONOMY,
                ),
                ChatMessage(role="assistant", content=combined),
                ChatMessage(
                    role="user",
                    content="""Adversarial review: an extra inference call may cost more than
the failed prompt and may repeat the Student's mistake. Identify which parts of your
design must be deterministic, when the semantic call is allowed, the maximum context
it receives, and a cheaper fallback candidate. Revise the recommendation if the
model-assisted step is not justified.""",
                ),
            ],
        )

    upper = _run(
        model,
        artifact,
        output_file,
        "e5_loop_upper_bound",
        VISIBLE_HOOKS
        + "\n"
        + CAPABILITY_SPACE
        + """

Analyze the expressive upper bound of this AgentLoop plus Hook architecture. Cover
which policies it can emulate, where context engineering and a bounded semantic call
are sufficient, and which systems fundamentally cannot be represented without core
changes. Include safety, ordering, rollback, latency, memory, concurrency, nested
planning, and causal-attribution limits.
""",
    )
    if upper is not None:
        _run_dialogue(
            model,
            artifact,
            output_file,
            "e5_upper_bound_red_team",
            [
                ChatMessage(role="system", content=SYSTEM),
                ChatMessage(role="assistant", content=upper),
                ChatMessage(
                    role="user",
                    content="""Red-team that analysis. Find places where it overstates Hook
expressiveness. Pay special attention to the fact that stage changes are synchronous,
must preserve payload type, current ModelInput edits are per-generation, persistent
state is per-rollout, tools are fixed, and the semantic call cannot run tools or a
nested loop. Return a corrected boundary map.""",
                ),
            ],
        )

    _run(
        model,
        artifact,
        output_file,
        "e6_non_prescriptive_guidance",
        CURRENT_EVIDENCE
        + "\n"
        + VISIBLE_HOOKS
        + "\n"
        + CAPABILITY_SPACE
        + "\n"
        + SYNTHETIC_HISTORY
        + """

Design a short, non-prescriptive capability disclosure and decision rubric for a
Critic and Compiler. It must make sophisticated mechanisms discoverable without
hard-coding 'use a model Hook'. It should encourage escalation only after repeated
mechanism-class failures and preserve room for deterministic solutions.
""",
    )
    print(f"Teacher mechanism probe written to: {output_file}")


def _run(
    model: OpenAICompatibleModel,
    artifact: dict[str, Any],
    output_file: Path,
    experiment_id: str,
    prompt: str,
) -> str | None:
    return _run_dialogue(
        model,
        artifact,
        output_file,
        experiment_id,
        [
            ChatMessage(role="system", content=SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
    )


def _run_dialogue(
    model: OpenAICompatibleModel,
    artifact: dict[str, Any],
    output_file: Path,
    experiment_id: str,
    messages: list[ChatMessage],
) -> str | None:
    print(f"Running {experiment_id}...")
    record: dict[str, Any] = {
        "experiment_id": experiment_id,
        "messages": [message.to_dict() for message in messages],
    }
    try:
        output = model.generate(ModelInput.from_messages(messages))
        record["output"] = output
        record["metadata"] = model.get_last_generation_metadata()
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        output = None
    artifact["experiments"].append(record)
    _write_artifact(output_file, artifact)
    return output


def _write_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _default_output_file() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return Path("adapter_logs") / f"teacher_mechanism_probe_{timestamp}.json"


if __name__ == "__main__":
    main()
