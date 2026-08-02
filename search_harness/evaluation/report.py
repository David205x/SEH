"""Evaluate runner JSONL records and write machine-readable offline reports."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from threading import local
from typing import Any

from tqdm import tqdm

from search_harness.datasets.identity import stable_example_id
from search_harness._internal import ordered_parallel_map

from .types import (
    EvaluationCase,
    StaticDecision,
    TaskEvaluator,
    TeacherJudgment,
)


def evaluate_rollout_file(
    rollout_file: Path,
    task_evaluator: TaskEvaluator,
    teacher_judge: Any | None = None,
    teacher_judge_factory: Callable[[], Any] | None = None,
    judge_workers: int = 1,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Evaluate each UTF-8 runner JSONL record without changing the rollout."""

    if teacher_judge is not None and teacher_judge_factory is not None:
        raise ValueError("teacher_judge and teacher_judge_factory are mutually exclusive")
    if judge_workers < 1:
        raise ValueError("judge_workers must be positive")
    if teacher_judge is not None and judge_workers > 1:
        raise ValueError(
            "parallel judging requires teacher_judge_factory for isolated models"
        )

    records = _read_jsonl(rollout_file)
    items: list[dict[str, Any]] = []
    pending: list[tuple[int, EvaluationCase]] = []
    judge_enabled = teacher_judge is not None or teacher_judge_factory is not None
    with tqdm(
        total=len(records),
        desc="Evaluation",
        unit="example",
        dynamic_ncols=True,
        disable=not show_progress,
    ) as progress:
        for record in records:
            item, teacher_case = _evaluate_record_static(
                record, task_evaluator, judge_enabled=judge_enabled
            )
            item_index = len(items)
            items.append(item)
            if teacher_case is None:
                progress.update(1)
            else:
                pending.append((item_index, teacher_case))

        if pending:
            thread_state = local()

            def judge_case(indexed_case: tuple[int, EvaluationCase]):
                _, case = indexed_case
                judge = teacher_judge
                if judge is None:
                    judge = getattr(thread_state, "judge", None)
                    if judge is None:
                        assert teacher_judge_factory is not None
                        judge = teacher_judge_factory()
                        thread_state.judge = judge
                return judge.judge(case)

            judgments = ordered_parallel_map(
                pending,
                judge_case,
                max_workers=judge_workers,
                max_in_flight=judge_workers * 2,
                on_complete=lambda _: progress.update(1),
            )
            for (item_index, _), judgment in zip(pending, judgments, strict=True):
                _apply_teacher_judgment(items[item_index], judgment)
    example_items = _aggregate_example_items(items)
    return {
        "schema_version": 1,
        "task": task_evaluator.task_name,
        "source_file": str(rollout_file),
        "created_at": datetime.now(UTC).isoformat(),
        "provenance": _shared_provenance(records),
        "evaluation_config": {
            "teacher_judge": judge_enabled,
            "judge_workers": judge_workers,
        },
        "metrics": _aggregate_metrics(items, example_items),
        "items": example_items,
        "rollouts": items,
    }


def write_evaluation_report(report: dict[str, Any], output_dir: Path) -> None:
    """Write a summary and item-level JSONL records using UTF-8."""

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        key: value for key, value in report.items() if key not in {"items", "rollouts"}
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "per_example.jsonl").open("w", encoding="utf-8") as file:
        for item in report["items"]:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")
    with (output_dir / "per_rollout.jsonl").open("w", encoding="utf-8") as file:
        for item in report["rollouts"]:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")
    (output_dir / "summary.md").write_text(
        _render_markdown_summary(summary["metrics"]), encoding="utf-8"
    )


def _evaluate_record_static(
    record: dict[str, Any],
    task_evaluator: TaskEvaluator,
    *,
    judge_enabled: bool,
) -> tuple[dict[str, Any], EvaluationCase | None]:
    example = record.get("example") if isinstance(record.get("example"), dict) else {}
    run = record.get("run") if isinstance(record.get("run"), dict) else None
    prediction = run.get("answer") if run is not None else None
    if not isinstance(prediction, str):
        prediction = None
    golden = example.get("answer")
    if not isinstance(golden, str):
        golden = None
    question = example.get("question") or (run or {}).get("question") or ""
    example_id = stable_example_id(example.get("example_id"), str(question))
    replicate = record.get("replicate")
    if replicate is None:
        replicate = {"replicate_id": "r000", "index": 0, "sampling_seed": None}
    if not isinstance(replicate, dict):
        raise TypeError("rollout replicate must be an object")
    replicate_id = replicate.get("replicate_id")
    if not isinstance(replicate_id, str) or not replicate_id.strip():
        raise ValueError("rollout replicate_id must be a non-empty string")
    case = EvaluationCase(example_id, str(question), golden, prediction)
    static = task_evaluator.evaluate_static(case)

    score: int | None
    score_source: str
    teacher_case: EvaluationCase | None = None
    if static.decision is StaticDecision.PASS:
        score, score_source = 1, "static"
    elif static.decision is StaticDecision.AUTOMATIC_ZERO:
        score, score_source = 0, "static"
    elif static.decision is StaticDecision.NEEDS_TEACHER and judge_enabled:
        score, score_source = None, "unresolved"
        teacher_case = case
    else:
        score, score_source = None, "unresolved"

    item = {
        "example_id": example_id,
        "replicate_id": replicate_id,
        "replicate_index": replicate.get("index"),
        "sampling_seed": replicate.get("sampling_seed"),
        "question": case.question,
        "golden_answer": golden,
        "predicted_answer": prediction,
        "run_status": run.get("status") if run is not None else None,
        "runner_error": record.get("runner_error"),
        "static": {
            "decision": static.decision.value,
            "metrics": static.metrics,
            "reason": static.reason,
        },
        "teacher": None,
        "score": score,
        "score_source": score_source,
        "execution": _execution_metrics(run),
    }
    return item, teacher_case


def _apply_teacher_judgment(
    item: dict[str, Any], judgment: TeacherJudgment
) -> None:
    item["teacher"] = judgment.to_dict()
    item["score"] = judgment.score
    item["score_source"] = (
        "teacher" if judgment.score is not None else "unresolved"
    )


def _execution_metrics(run: dict[str, Any] | None) -> dict[str, Any]:
    if run is None:
        return {
            "steps": None,
            "model_calls": 0,
            "tool_calls": 0,
            "retriever_errors": 0,
            "duplicate_queries": 0,
            "tokens": {},
        }
    state = run.get("state") if isinstance(run.get("state"), dict) else {}
    interactions = state.get("tool_interactions") if isinstance(state.get("tool_interactions"), list) else []
    queries: list[str] = []
    retriever_errors = 0
    for interaction in interactions:
        if not isinstance(interaction, dict):
            continue
        call = interaction.get("tool_call") if isinstance(interaction.get("tool_call"), dict) else {}
        result = interaction.get("tool_result") if isinstance(interaction.get("tool_result"), dict) else {}
        arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        query = arguments.get("query")
        if isinstance(query, str):
            queries.append(query.strip().casefold())
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        if metadata.get("error"):
            retriever_errors += 1
    return {
        "steps": state.get("step"),
        "model_calls": len(state.get("model_outputs", [])),
        "tool_calls": len(interactions),
        "retriever_errors": retriever_errors,
        "duplicate_queries": len(queries) - len(set(queries)),
        "tokens": _trace_token_usage(run.get("trace")),
    }


def _trace_token_usage(trace: object) -> dict[str, int]:
    totals: Counter[str] = Counter()
    if not isinstance(trace, list):
        return dict(totals)
    for event in trace:
        if not isinstance(event, dict) or event.get("event_type") not in {
            "model_output",
            "hook_model_output",
        }:
            continue
        namespace = "hook" if event.get("event_type") == "hook_model_output" else "student"
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        if usage is None:
            usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else {}
        input_tokens = usage.get("prompt_tokens", usage.get("prompt_eval_count"))
        output_tokens = usage.get("completion_tokens", usage.get("eval_count"))
        total_tokens = usage.get("total_tokens")
        if isinstance(input_tokens, int):
            totals["input_tokens"] += input_tokens
            totals[f"{namespace}_input_tokens"] += input_tokens
        if isinstance(output_tokens, int):
            totals["output_tokens"] += output_tokens
            totals[f"{namespace}_output_tokens"] += output_tokens
        if isinstance(total_tokens, int):
            totals["total_tokens"] += total_tokens
            totals[f"{namespace}_total_tokens"] += total_tokens
    if "total_tokens" not in totals and ("input_tokens" in totals or "output_tokens" in totals):
        totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    for namespace in ("student", "hook"):
        total_key = f"{namespace}_total_tokens"
        input_key = f"{namespace}_input_tokens"
        output_key = f"{namespace}_output_tokens"
        if total_key not in totals and (
            input_key in totals or output_key in totals
        ):
            totals[total_key] = totals[input_key] + totals[output_key]
    return dict(totals)


def _aggregate_metrics(
    items: list[dict[str, Any]], example_items: list[dict[str, Any]]
) -> dict[str, Any]:
    scores = [item["score"] for item in items if item["score"] in {0, 1}]
    executions = [item["execution"] for item in items]
    statuses = Counter(item["run_status"] or "runner_error" for item in items)
    token_totals: Counter[str] = Counter()
    token_covered = 0
    for execution in executions:
        tokens = execution["tokens"]
        if tokens:
            token_covered += 1
            token_totals.update(tokens)
    return {
        "answers": {
            "scored_count": len(scores),
            "correct_count": sum(scores),
            "accuracy": sum(scores) / len(scores) if scores else None,
            "static_pass_count": sum(item["score_source"] == "static" and item["score"] == 1 for item in items),
            "teacher_judged_count": sum(item["score_source"] == "teacher" for item in items),
            "unresolved_count": sum(item["score"] is None for item in items),
            "example_count": len(example_items),
            "stable_correct_count": sum(
                item["stability"] == "stable_correct" for item in example_items
            ),
            "stable_failure_count": sum(
                item["stability"] == "stable_failure" for item in example_items
            ),
            "unstable_count": sum(
                item["stability"] == "unstable" for item in example_items
            ),
            "unresolved_example_count": sum(
                item["stability"] == "unresolved" for item in example_items
            ),
            "stable_correct_rate": _rate(
                item["stability"] == "stable_correct" for item in example_items
            ),
            "stable_failure_rate": _rate(
                item["stability"] == "stable_failure" for item in example_items
            ),
            "unstable_rate": _rate(
                item["stability"] == "unstable" for item in example_items
            ),
            "majority_correct_rate": _rate(
                item["majority_correct"] is True for item in example_items
            ),
            "pass_at_n": _rate(
                item["any_correct"] is True for item in example_items
            ),
            "mean_example_success_rate": _mean(
                item["success_rate"] for item in example_items
            ),
            "mean_answer_consistency": _mean(
                item["answer_consistency"] for item in example_items
            ),
        },
        "execution": {
            "record_count": len(items),
            "completed_rate": statuses["completed"] / len(items) if items else None,
            "status_counts": dict(statuses),
            "retriever_error_rate": sum(item["retriever_errors"] > 0 for item in executions) / len(items) if items else None,
            "mean_steps": _mean(execution["steps"] for execution in executions),
            "mean_model_calls": _mean(execution["model_calls"] for execution in executions),
            "mean_tool_calls": _mean(execution["tool_calls"] for execution in executions),
            "mean_duplicate_queries": _mean(execution["duplicate_queries"] for execution in executions),
        },
        "tokens": {
            "input_tokens": token_totals.get("input_tokens"),
            "output_tokens": token_totals.get("output_tokens"),
            "total_tokens": token_totals.get("total_tokens"),
            "student_input_tokens": token_totals.get("student_input_tokens"),
            "student_output_tokens": token_totals.get("student_output_tokens"),
            "student_total_tokens": token_totals.get("student_total_tokens"),
            "hook_input_tokens": token_totals.get("hook_input_tokens"),
            "hook_output_tokens": token_totals.get("hook_output_tokens"),
            "hook_total_tokens": token_totals.get("hook_total_tokens"),
            "coverage_rate": token_covered / len(items) if items else None,
        },
    }


def _aggregate_example_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: list[str] = []
    for item in items:
        example_id = str(item["example_id"])
        if example_id not in grouped:
            order.append(example_id)
        grouped[example_id].append(item)

    result: list[dict[str, Any]] = []
    for example_id in order:
        replicates = grouped[example_id]
        _validate_replicates(example_id, replicates)
        scores = [item["score"] for item in replicates if item["score"] in {0, 1}]
        correct = sum(scores)
        unresolved = len(replicates) - len(scores)
        success_rate = correct / len(scores) if scores else None
        if unresolved:
            stability = "unresolved"
            score = None
        elif correct == len(replicates):
            stability = "stable_correct"
            score = 1
        elif correct == 0:
            stability = "stable_failure"
            score = 0
        else:
            stability = "unstable"
            score = None
        predictions = [
            item["predicted_answer"]
            for item in replicates
            if isinstance(item.get("predicted_answer"), str)
        ]
        normalized_predictions = [value.strip().casefold() for value in predictions]
        original_by_normalized = {
            value.strip().casefold(): value for value in predictions
        }
        answer_counts = Counter(normalized_predictions)
        modal_key = answer_counts.most_common(1)[0][0] if answer_counts else None
        modal_answer = (
            original_by_normalized[modal_key] if modal_key is not None else None
        )
        answer_consistency = (
            answer_counts[modal_key] / len(normalized_predictions)
            if modal_key is not None
            else None
        )
        statuses = Counter(
            item.get("run_status") or "runner_error" for item in replicates
        )
        compact_replicates = [_compact_rollout_result(item) for item in replicates]
        result.append(
            {
                "example_id": example_id,
                "question": replicates[0]["question"],
                "golden_answer": replicates[0]["golden_answer"],
                "predicted_answer": modal_answer,
                "score": score,
                "score_source": "aggregate",
                "stability": stability,
                "requested_rollouts": len(replicates),
                "completed_rollouts": statuses.get("completed", 0),
                "scored_rollouts": len(scores),
                "correct_count": correct,
                "unresolved_count": unresolved,
                "success_rate": success_rate,
                "score_std": (
                    math.sqrt(success_rate * (1 - success_rate))
                    if success_rate is not None
                    else None
                ),
                "all_correct": score == 1,
                "any_correct": correct > 0,
                "majority_correct": (
                    success_rate > 0.5 if success_rate is not None else None
                ),
                "answer_consistency": answer_consistency,
                "answer_distribution": dict(answer_counts),
                "run_status": (
                    next(iter(statuses)) if len(statuses) == 1 else "mixed"
                ),
                "run_status_counts": dict(statuses),
                "failed_replicate_ids": [
                    item["replicate_id"] for item in replicates if item["score"] == 0
                ],
                "unresolved_replicate_ids": [
                    item["replicate_id"]
                    for item in replicates
                    if item["score"] is None
                ],
                "execution": _aggregate_execution(replicates),
                "replicates": compact_replicates,
            }
        )
    return result


def _validate_replicates(
    example_id: str, replicates: list[dict[str, Any]]
) -> None:
    replicate_ids = [item["replicate_id"] for item in replicates]
    if len(replicate_ids) != len(set(replicate_ids)):
        raise ValueError(f"duplicate rollout replicate for example_id: {example_id}")
    questions = {item["question"] for item in replicates}
    golden_answers = {item["golden_answer"] for item in replicates}
    if len(questions) != 1 or len(golden_answers) != 1:
        raise ValueError(f"replicates disagree on example content: {example_id}")


def _compact_rollout_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "replicate_id",
            "replicate_index",
            "sampling_seed",
            "predicted_answer",
            "run_status",
            "runner_error",
            "score",
            "score_source",
            "static",
            "teacher",
            "execution",
        )
    }


def _aggregate_execution(replicates: list[dict[str, Any]]) -> dict[str, Any]:
    executions = [item["execution"] for item in replicates]
    return {
        "mean_steps": _mean(item.get("steps") for item in executions),
        "mean_model_calls": _mean(item.get("model_calls") for item in executions),
        "mean_tool_calls": _mean(item.get("tool_calls") for item in executions),
        "retriever_errors": sum(
            item.get("retriever_errors", 0) for item in executions
        ),
        "mean_duplicate_queries": _mean(
            item.get("duplicate_queries") for item in executions
        ),
    }


def _rate(values: Any) -> float | None:
    present = list(values)
    return sum(present) / len(present) if present else None


def _mean(values: Any) -> float | None:
    present = [value for value in values if isinstance(value, (int, float))]
    return mean(present) if present else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            if not raw_line.strip():
                continue
            value = json.loads(raw_line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            records.append(value)
    return records


def _shared_provenance(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the one rollout configuration shared by this evaluated batch."""

    values = [record.get("provenance") for record in records]
    if not values or all(value is None for value in values):
        return None
    if any(not isinstance(value, dict) for value in values):
        raise ValueError("rollout provenance must be present and an object on every record")
    serialized = {json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values}
    if len(serialized) != 1:
        raise ValueError("rollout records have inconsistent experiment provenance")
    return dict(values[0])


def _render_markdown_summary(metrics: dict[str, Any]) -> str:
    answers = metrics["answers"]
    execution = metrics["execution"]
    return (
        "# Evaluation Summary\n\n"
        f"- Accuracy: {answers['accuracy']} ({answers['correct_count']}/{answers['scored_count']})\n"
        f"- Unresolved: {answers['unresolved_count']}\n"
        f"- Stable correct rate: {answers['stable_correct_rate']}\n"
        f"- Unstable rate: {answers['unstable_rate']}\n"
        f"- Completed rate: {execution['completed_rate']}\n"
        f"- Mean steps: {execution['mean_steps']}\n"
        f"- Mean tool calls: {execution['mean_tool_calls']}\n"
    )
