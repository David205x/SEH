"""Repair protocol-only outputs and verify final answers against retrieved evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from search_harness.framework import (
    BaseHook,
    ChatMessage,
    FinalDecision,
    HookContext,
    HookModelRequest,
    HookPhase,
    ModelInput,
    StateRef,
)


class ProtocolRepairHook(BaseHook):
    """Wrap short plain-text answers after retrieval in the tagged protocol."""

    def __init__(self) -> None:
        super().__init__(
            hook_id="protocol_repair",
            phases=frozenset({HookPhase.POST_MODEL}),
            writable_stage_keys=frozenset({"stage.raw_model_output"}),
        )

    def handle(self, context: HookContext) -> None:
        raw = context.state.get("stage.raw_model_output")
        core = context.state.get("core")
        if not isinstance(raw, str) or not isinstance(core, dict):
            raise TypeError("protocol repair requires string output and core state")
        text = raw.strip()
        if "<tool_call>" in text or "<final_answer>" in text:
            return
        if not core.get("tool_interactions") or not text:
            return
        if len(text) <= 300 and len(text.split()) <= 40 and not text.startswith("{"):
            context.state.set(
                "stage.raw_model_output", f"<final_answer>{text}</final_answer>"
            )


class AnswerVerifierHook(BaseHook):
    """Use the Student model itself as a bounded evidence-grounded final checker."""

    RETRY_KEY = "extension.answer_verifier.retries"

    def __init__(
        self,
        *,
        verifier_prompt: str,
        max_evidence_chars: int,
        max_retries: int,
    ) -> None:
        self._verifier_prompt = verifier_prompt.strip()
        self._max_evidence_chars = max_evidence_chars
        self._max_retries = max_retries
        super().__init__(
            hook_id="answer_verifier",
            phases=frozenset({HookPhase.PRE_FINAL}),
            state_refs=(
                StateRef(
                    key=self.RETRY_KEY,
                    owner="answer_verifier",
                    value_type=int,
                    writers=frozenset({"answer_verifier"}),
                    default=0,
                ),
            ),
            writable_stage_keys=frozenset({"stage.final_decision"}),
            model_profiles=frozenset({"student"}),
        )

    def handle(self, context: HookContext) -> None:
        decision = context.state.get("stage.final_decision")
        core = context.state.get("core")
        if not isinstance(decision, FinalDecision) or not isinstance(core, dict):
            raise TypeError("answer verifier requires FinalDecision and core state")
        candidate = decision.answer
        if candidate is None:
            raise ValueError("accepted candidate is missing")
        evidence = _render_evidence(core, self._max_evidence_chars)
        if not evidence:
            return
        question = core.get("question")
        if not isinstance(question, str):
            raise TypeError("core.question must be a string")
        response = context.call_model(
            HookModelRequest(
                profile="student",
                purpose="verify_final_answer_against_evidence",
                model_input=ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content=self._verifier_prompt),
                        ChatMessage(
                            role="user",
                            content=(
                                f"Question:\n{question}\n\n"
                                f"Candidate answer:\n{candidate}\n\n"
                                f"Retrieved evidence:\n{evidence}"
                            ),
                        ),
                    ]
                ),
            )
        )
        result = _parse_json_object(response.raw_output)
        verdict = str(result.get("verdict", "")).strip().casefold()
        answer = result.get("answer")
        if verdict in {"accept", "replace"} and isinstance(answer, str) and answer.strip():
            context.state.set("stage.final_decision", FinalDecision.accept(answer.strip()))
            return
        retries = context.state.get(self.RETRY_KEY)
        if verdict == "retry" and isinstance(retries, int) and retries < self._max_retries:
            feedback = result.get("feedback")
            if not isinstance(feedback, str) or not feedback.strip():
                feedback = "The candidate is not yet supported. Retrieve the missing relation."
            context.state.set(self.RETRY_KEY, retries + 1)
            context.state.set("stage.final_decision", FinalDecision.defer(feedback))


def _render_evidence(core: dict[str, Any], limit: int) -> str:
    blocks: list[str] = []
    for interaction in core.get("tool_interactions", []):
        if not isinstance(interaction, dict):
            continue
        call = interaction.get("tool_call") or {}
        result = interaction.get("tool_result") or {}
        query = (call.get("arguments") or {}).get("query", "")
        content = result.get("content", "")
        if isinstance(content, str):
            blocks.append(f"QUERY: {query}\n{content}")
    text = "\n\n".join(blocks)
    if len(text) <= limit:
        return text
    head = max(1, limit // 3)
    return f"{text[:head]}\n\n[...middle omitted...]\n\n{text[-(limit-head):]}"


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip().strip("`").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def build(config: dict[str, Any], context: Any) -> tuple[BaseHook, BaseHook]:
    del context
    allowed = {"max_evidence_chars", "max_retries"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unsupported answer_control config keys: {sorted(unknown)}")
    max_evidence_chars = config.get("max_evidence_chars", 14000)
    max_retries = config.get("max_retries", 1)
    if not isinstance(max_evidence_chars, int) or max_evidence_chars < 1000:
        raise ValueError("max_evidence_chars must be an integer >= 1000")
    if not isinstance(max_retries, int) or max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer")
    prompt = Path(__file__).resolve().with_name("verifier.md").read_text(encoding="utf-8")
    return (
        ProtocolRepairHook(),
        AnswerVerifierHook(
            verifier_prompt=prompt,
            max_evidence_chars=max_evidence_chars,
            max_retries=max_retries,
        ),
    )
