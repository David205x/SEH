"""Re-judge every rollout and classify the resulting assessment corpus once."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Sequence

from tqdm import tqdm

from experiments.teacher_query_views.judge import ShadowTeacherBinaryJudge
from search_harness._internal import (
    read_runtime_config,
    teacher_judge_thinking_mode,
)
from search_harness.evaluation import EvaluationCase, HotpotQAEvaluator
from search_harness.framework import ChatMessage, ModelInput
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
)


_CLASSIFIER_SYSTEM_PROMPT = """You analyze an exhaustive corpus of result-level
Teacher judgments. The input contains one compact JSON object per rollout.

Work only at the answer-result level. Do not infer retrieval behavior, stopping
behavior, hidden reasoning, prompt defects, or causal mechanisms because no
Student trajectory is provided.

Return exactly one JSON object with no markdown using this schema:
{
  "quality_audit": {
    "overall_assessment": "string",
    "strengths": ["string"],
    "weaknesses": ["string"],
    "ambiguous_or_low_information_refs": [
      {"ref": "example_id/replicate_id", "reason": "string"}
    ]
  },
  "failure_categories": [
    {
      "category_id": "C1",
      "label": "short result-level label",
      "definition": "observable answer-level inclusion rule",
      "representative_refs": ["example_id/replicate_id"]
    }
  ],
  "failure_assignments": [
    {"ref": "example_id/replicate_id", "category_id": "C1"}
  ],
  "correct_answer_basis_summary": ["string"],
  "limits": ["string"]
}

Create 5 to 12 mutually exclusive categories. Assign every rollout whose
`shadow_score` is 0 exactly once, assign no rollout whose `shadow_score` is 1,
and use only refs present in the input. Base categories on the assessment text,
question, reference answer, and predicted answer. Keep aliases/equivalent
wording distinct from wrong entity, wrong relation or attribute, incomplete
multi-part answer, unsupported/non-answer, and scoring ambiguity when the data
supports those distinctions. Do not turn result labels into behavior causes."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-rollout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--judge-thinking-mode",
        choices=("inherit", "enabled", "disabled"),
        default="inherit",
        help="Override thinking for every per-rollout shadow Judge call.",
    )
    parser.add_argument(
        "--classifier-max-tokens",
        type=int,
        default=8192,
    )
    parser.add_argument(
        "--classifier-thinking-mode",
        choices=("inherit", "enabled", "disabled"),
        default="inherit",
        help="Override thinking only for the one-shot classification call.",
    )
    parser.add_argument(
        "--skip-classification",
        action="store_true",
        help="Generate or reuse per-rollout judgments without the final call.",
    )
    parser.add_argument(
        "--classification-only",
        action="store_true",
        help="Reuse completed judgments and rerun only the final classification.",
    )
    parser.add_argument(
        "--reuse-classification",
        action="store_true",
        help="Reuse classification.json when rebuilding deterministic metrics.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if args.max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    if args.classifier_max_tokens < 1:
        raise ValueError("classifier_max_tokens must be positive")

    source_path = args.per_rollout.resolve()
    output_dir = args.output_dir.resolve()
    judgment_dir = output_dir / "judgments"
    judgment_dir.mkdir(parents=True, exist_ok=True)
    source_items = _read_jsonl(source_path)
    model_config = OpenAICompatibleConfig.from_env(
        env_file=args.env_file,
        prefix="TEACHER",
    )
    configured_judge_thinking = teacher_judge_thinking_mode(
        read_runtime_config(env_file=args.env_file),
        default=model_config.thinking_mode,
    )
    judge_config = replace(
        model_config,
        thinking_mode=(
            configured_judge_thinking
            if args.judge_thinking_mode == "inherit"
            else args.judge_thinking_mode
        ) if model_config.thinking_mode is not None else None,
    )

    if args.classification_only:
        judgment_items = _load_completed_judgments(
            source_count=len(source_items),
            judgment_dir=judgment_dir,
        )
    else:
        judgment_items = _judge_all(
            source_items=source_items,
            judgment_dir=judgment_dir,
            model_config=judge_config,
            workers=args.workers,
            max_attempts=args.max_attempts,
        )
    _write_jsonl(output_dir / "judgments.jsonl", judgment_items)

    corpus = build_classification_corpus(judgment_items)
    (output_dir / "classification_input.jsonl").write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":"))
            for item in corpus
        )
        + "\n",
        encoding="utf-8",
    )
    classifier_config = replace(
        model_config,
        max_tokens=args.classifier_max_tokens,
        thinking_mode=(
            model_config.thinking_mode
            if args.classifier_thinking_mode == "inherit"
            else args.classifier_thinking_mode
        ),
    )
    classification = None
    if args.reuse_classification:
        classification = _read_json(output_dir / "classification.json")
    elif not args.skip_classification:
        classification = _classify_once(
            corpus=corpus,
            config=classifier_config,
        )
        _write_json(output_dir / "classification.json", classification)

    summary = build_summary(
        source_path=source_path,
        model_config=judge_config,
        judgments=judgment_items,
        classification=classification,
        corpus=corpus,
        classifier_config=classifier_config,
    )
    _write_json(output_dir / "summary.json", summary)
    return summary


def build_classification_corpus(
    judgments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project all judgments into one compact, result-level classifier input."""

    return [
        {
            "ref": item["ref"],
            "question": item["case"]["question"],
            "reference_answer": item["case"]["golden_answer"],
            "predicted_answer": item["case"]["predicted_answer"],
            "original_score": item["original"]["score"],
            "original_score_source": item["original"]["score_source"],
            "shadow_score": item["shadow"]["score"],
            "assessment": item["shadow"]["assessment"],
        }
        for item in judgments
        if item["shadow"].get("error") is None
    ]


def build_summary(
    *,
    source_path: Path,
    model_config: OpenAICompatibleConfig,
    judgments: list[dict[str, Any]],
    classification: dict[str, Any] | None,
    corpus: list[dict[str, Any]],
    classifier_config: OpenAICompatibleConfig,
) -> dict[str, Any]:
    """Build deterministic coverage, agreement, quality, and token metrics."""

    completed = [
        item for item in judgments if item["shadow"].get("error") is None
    ]
    errors = [item for item in judgments if item not in completed]
    assessments = [str(item["shadow"]["assessment"]) for item in completed]
    agreement = [
        item
        for item in completed
        if item["shadow"]["score"] == item["original"]["score"]
    ]
    usage = [
        attempt_usage
        for item in judgments
        for attempt_usage in _attempt_usage(item)
        if attempt_usage
    ]
    classification_validation = (
        validate_classification(classification, corpus)
        if classification is not None
        else None
    )
    return {
        "schema_version": 1,
        "experiment": "shadow_teacher_judge_landscape_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source_per_rollout": str(source_path),
        "model": model_config.provenance(),
        "coverage": {
            "source_rollouts": len(judgments),
            "completed": len(completed),
            "failed": len(errors),
            "classification_input_items": len(corpus),
            "shadow_score_counts": dict(
                Counter(str(item["shadow"]["score"]) for item in completed)
            ),
        },
        "score_agreement": {
            "overall": _ratio(len(agreement), len(completed)),
            "by_original_source": _agreement_by_source(completed),
            "disagreement_refs": [
                item["ref"]
                for item in completed
                if item["shadow"]["score"] != item["original"]["score"]
            ],
        },
        "assessment_text": {
            "count": len(assessments),
            "mean_characters": _mean(len(item) for item in assessments),
            "median_characters": _median(len(item) for item in assessments),
            "min_characters": min(map(len, assessments), default=None),
            "max_characters": max(map(len, assessments), default=None),
            "unique_count": len(set(assessments)),
            "exact_duplicate_count": len(assessments) - len(set(assessments)),
            "over_240_characters": sum(len(item) > 240 for item in assessments),
        },
        "judge_api_usage": _aggregate_usage(usage),
        "classification": {
            "attempted": classification is not None,
            "model": (
                classifier_config.provenance()
                if classification is not None
                else None
            ),
            "input_characters": len(
                "\n".join(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                    for item in corpus
                )
            ),
            "usage": (
                classification.get("usage")
                if isinstance(classification, dict)
                else None
            ),
            "validation": classification_validation,
        },
        "failed_refs": [item["ref"] for item in errors],
    }


def validate_classification(
    result: dict[str, Any],
    corpus: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate one-shot assignments without repairing the model output."""

    payload = result.get("parsed_output")
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "errors": ["classification output was not parsed as an object"],
        }
    categories = payload.get("failure_categories")
    assignments = payload.get("failure_assignments")
    categories = categories if isinstance(categories, list) else []
    assignments = assignments if isinstance(assignments, list) else []
    category_ids = {
        item.get("category_id")
        for item in categories
        if isinstance(item, dict) and isinstance(item.get("category_id"), str)
    }
    expected = {
        item["ref"] for item in corpus if item.get("shadow_score") == 0
    }
    correct = {
        item["ref"] for item in corpus if item.get("shadow_score") == 1
    }
    refs = [
        item.get("ref")
        for item in assignments
        if isinstance(item, dict) and isinstance(item.get("ref"), str)
    ]
    assigned = set(refs)
    unknown_categories = sorted(
        {
            str(item.get("category_id"))
            for item in assignments
            if isinstance(item, dict)
            and item.get("category_id") not in category_ids
        }
    )
    errors = []
    if expected - assigned:
        errors.append(f"missing failure refs: {sorted(expected - assigned)}")
    if assigned - expected:
        errors.append(f"non-failure or unknown refs assigned: {sorted(assigned - expected)}")
    if len(refs) != len(assigned):
        errors.append("duplicate failure refs were assigned")
    if unknown_categories:
        errors.append(f"unknown category IDs: {unknown_categories}")
    if assigned & correct:
        errors.append("correct rollouts were assigned to failure categories")
    counts = Counter(
        str(item.get("category_id"))
        for item in assignments
        if isinstance(item, dict)
        and item.get("ref") in expected
        and item.get("category_id") in category_ids
    )
    return {
        "valid": not errors,
        "expected_failure_count": len(expected),
        "assignment_count": len(assignments),
        "unique_assigned_failure_count": len(assigned & expected),
        "category_count": len(category_ids),
        "category_counts": dict(sorted(counts.items())),
        "errors": errors,
    }


def _judge_all(
    *,
    source_items: list[dict[str, Any]],
    judgment_dir: Path,
    model_config: OpenAICompatibleConfig,
    workers: int,
    max_attempts: int,
) -> list[dict[str, Any]]:
    indexed = list(enumerate(source_items, start=1))
    results: dict[int, dict[str, Any]] = {}
    pending = []
    for index, item in indexed:
        path = judgment_dir / f"judgment_{index:04d}.json"
        if path.exists():
            results[index] = _read_json(path)
        else:
            pending.append((index, item, path))

    def invoke(task: tuple[int, dict[str, Any], Path]) -> tuple[int, dict[str, Any]]:
        index, item, path = task
        result = _judge_one(
            index=index,
            item=item,
            model_config=model_config,
            max_attempts=max_attempts,
        )
        _write_json(path, result)
        return index, result

    if pending:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(invoke, item): item[0] for item in pending}
            with tqdm(total=len(pending), desc="Shadow Teacher Judge", unit="rollout") as progress:
                for future in as_completed(futures):
                    index, result = future.result()
                    results[index] = result
                    progress.update(1)
    return [results[index] for index, _ in indexed]


def _load_completed_judgments(
    *,
    source_count: int,
    judgment_dir: Path,
) -> list[dict[str, Any]]:
    values = []
    for index in range(1, source_count + 1):
        path = judgment_dir / f"judgment_{index:04d}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"classification-only requires completed judgment: {path}"
            )
        values.append(_read_json(path))
    return values


def _judge_one(
    *,
    index: int,
    item: dict[str, Any],
    model_config: OpenAICompatibleConfig,
    max_attempts: int,
) -> dict[str, Any]:
    case = EvaluationCase(
        example_id=str(item.get("example_id")),
        question=str(item.get("question") or ""),
        golden_answer=_optional_string(item.get("golden_answer")),
        predicted_answer=_optional_string(item.get("predicted_answer")),
    )
    attempts = []
    for _ in range(max_attempts):
        judgment = ShadowTeacherBinaryJudge(
            OpenAICompatibleModel(model_config),
            HotpotQAEvaluator(),
        ).judge(case)
        payload = asdict(judgment)
        attempts.append(payload)
        if judgment.error is None:
            break
    shadow = attempts[-1]
    replicate_id = str(item.get("replicate_id"))
    return {
        "schema_version": 1,
        "index": index,
        "ref": f"{case.example_id}/{replicate_id}",
        "case": {
            "example_id": case.example_id,
            "replicate_id": replicate_id,
            "question": case.question,
            "golden_answer": case.golden_answer,
            "predicted_answer": case.predicted_answer,
        },
        "original": {
            "score": item.get("score"),
            "score_source": item.get("score_source"),
            "static": item.get("static"),
            "teacher": item.get("teacher"),
        },
        "shadow": shadow,
        "attempt_count": len(attempts),
        "attempts": attempts,
    }


def _classify_once(
    *,
    corpus: list[dict[str, Any]],
    config: OpenAICompatibleConfig,
) -> dict[str, Any]:
    input_text = "\n".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        for item in corpus
    )
    counts = Counter(item.get("shadow_score") for item in corpus)
    user_prompt = (
        f"The corpus contains {len(corpus)} rollouts: "
        f"{counts.get(0, 0)} with shadow_score=0 and "
        f"{counts.get(1, 0)} with shadow_score=1.\n\n"
        "Exhaustive judgment corpus follows as JSONL:\n"
        f"{input_text}"
    )
    model = OpenAICompatibleModel(config)
    response = model.generate(
        ModelInput.from_messages(
            [
                ChatMessage(role="system", content=_CLASSIFIER_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_prompt),
            ]
        )
    )
    parsed = None
    parse_error = None
    try:
        parsed = _parse_json_object(response.raw_output)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        parse_error = f"{type(exc).__name__}: {exc}"
    return {
        "raw_output": response.raw_output,
        "parsed_output": parsed,
        "parse_error": parse_error,
        "usage": dict(response.usage),
        "metadata": dict(response.metadata),
    }


def _parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError("classification output must be one JSON object")
    return parsed


def _agreement_by_source(items: list[dict[str, Any]]) -> dict[str, Any]:
    sources: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        sources.setdefault(str(item["original"]["score_source"]), []).append(item)
    return {
        source: {
            "count": len(selected),
            "agreement": _ratio(
                sum(
                    item["shadow"]["score"] == item["original"]["score"]
                    for item in selected
                ),
                len(selected),
            ),
        }
        for source, selected in sorted(sources.items())
    }


def _aggregate_usage(items: list[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted({key for item in items for key in item if isinstance(item.get(key), int)})
    result = {
        "request_count": len(items),
        "totals": {key: sum(int(item.get(key, 0)) for item in items) for key in keys},
        "means": {key: _mean(int(item.get(key, 0)) for item in items) for key in keys},
    }
    reasoning_tokens = [
        details.get("reasoning_tokens")
        for item in items
        for details in [item.get("completion_tokens_details")]
        if isinstance(details, dict)
        and isinstance(details.get("reasoning_tokens"), int)
    ]
    result["reasoning_tokens"] = {
        "covered_requests": len(reasoning_tokens),
        "total": sum(reasoning_tokens),
        "mean": _mean(reasoning_tokens),
    }
    return result


def _usage(shadow: dict[str, Any]) -> dict[str, Any]:
    metadata = shadow.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    usage = metadata.get("usage")
    return usage if isinstance(usage, dict) else {}


def _attempt_usage(item: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = item.get("attempts")
    if not isinstance(attempts, list):
        return [_usage(item.get("shadow", {}))]
    return [
        _usage(attempt)
        for attempt in attempts
        if isinstance(attempt, dict)
    ]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"JSONL line {line_number} must be an object")
            values.append(value)
    return values


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values),
        encoding="utf-8",
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _mean(values) -> float | None:
    selected = list(values)
    return round(mean(selected), 2) if selected else None


def _median(values) -> float | None:
    selected = list(values)
    return round(float(median(selected)), 2) if selected else None


def main(argv: Sequence[str] | None = None) -> None:
    summary = run(parse_args(argv))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
