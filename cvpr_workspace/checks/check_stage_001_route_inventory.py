"""核对 STAGE-001 route inventory 与当前 Controller 源码的一致性。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_SPECIAL_GROUPS = {
    "controller_lifecycle",
    "research_revision_helper",
}
REQUIRED_BRANCH_FIELDS = {
    "id",
    "trigger",
    "next",
    "obligation",
    "outcome_state",
    "terminal_source",
}


def parse_args() -> argparse.Namespace:
    """解析可选的结构化检查输出位置。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="相对项目根目录或绝对的 JSON 检查结果路径",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON root must be an object: {path}")
    return value


def _source_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _work_kinds(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "WorkKind":
            values: set[str] = set()
            for item in node.body:
                if not isinstance(item, ast.Assign):
                    continue
                if not isinstance(item.value, ast.Constant):
                    continue
                if not isinstance(item.value.value, str):
                    continue
                values.add(item.value.value)
            return values
    raise AssertionError("WorkKind enum was not found")


def _completed_handlers(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "_CompletedTransition":
            return {
                item.name.removeprefix("on_")
                for item in node.body
                if isinstance(item, ast.FunctionDef)
                and item.name.startswith("on_")
            }
    raise AssertionError("_CompletedTransition class was not found")


def _call_count(tree: ast.Module, attribute_name: str) -> int:
    return sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute_name
        for node in ast.walk(tree)
    )


def _complete_reason_count(tree: ast.Module) -> int:
    return sum(
        isinstance(node, ast.keyword) and node.arg == "complete_reason"
        for node in ast.walk(tree)
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_markers(root: Path, groups: list[dict[str, Any]]) -> None:
    for group in groups:
        source_ref = str(group["source_ref"])
        relative_path = source_ref.split("#", maxsplit=1)[0]
        source_path = root / relative_path
        source = source_path.read_text(encoding="utf-8")
        for marker in group["source_markers"]:
            if marker not in source:
                raise AssertionError(
                    f"missing source marker for {group['id']}: {marker}"
                )


def _assert_semantic_markers(root: Path) -> None:
    required = {
        "search_harness/evolution/research/roles/contracts.py": {
            'EvidenceDecision = Literal["continue", "revise", "reject", '
            '"ready_to_distill"]',
            '"needs_spec_revision"',
            '"needs_research_revision"',
            'CandidateRecommendation = Literal["accept", "revise", "reject"]',
            '"implementation_blocked"',
        },
        "search_harness/evolution/control/controller.py": {
            '"work_failed"',
            '"run_paused"',
            '"run_resumed"',
            "_recover_interrupted_work",
            '"trajectory_settled"',
            "materialize_settlement(",
        },
        "search_harness/evolution/control/domain.py": {
            "class SettlementScope",
            "class TrajectoryLineage",
            "def materialize_settlement(",
        },
        "search_harness/evolution/control/journal.py": {
            "project_events([*existing, *events])",
            "os.replace(temporary, target)",
        },
        "search_harness/evolution/control/candidate_version_effects.py": {
            "promotion_result_if_completed",
            "rejection_result_if_completed",
            '"unchanged_rejected_candidate"',
        },
    }
    for relative_path, markers in required.items():
        source = (root / relative_path).read_text(encoding="utf-8")
        missing = sorted(marker for marker in markers if marker not in source)
        if missing:
            raise AssertionError(
                f"semantic source markers missing in {relative_path}: {missing}"
            )


def run_check(root: Path) -> dict[str, Any]:
    """执行静态路由、终态数量和审计边界核对。"""

    matrix_path = (
        root
        / "cvpr_workspace"
        / "analysis"
        / "stage_001_route_coverage_matrix.json"
    )
    audit_path = (
        root
        / "cvpr_workspace"
        / "analysis"
        / "stage_001_h1_h2_semantic_diff_audit.md"
    )
    domain_tree = _source_tree(
        root / "search_harness" / "evolution" / "control" / "domain.py"
    )
    transitions_tree = _source_tree(
        root / "search_harness" / "evolution" / "control" / "transitions.py"
    )
    matrix = _load_json(matrix_path)
    expectations = matrix["static_inventory_expectations"]
    groups = matrix["route_groups"]
    if not isinstance(groups, list):
        raise TypeError("route_groups must be a list")

    work_kinds = _work_kinds(domain_tree)
    handlers = _completed_handlers(transitions_tree)
    if work_kinds != handlers:
        raise AssertionError(
            "WorkKind and completed transition handlers differ: "
            f"work_kinds={sorted(work_kinds)}, handlers={sorted(handlers)}"
        )
    if len(work_kinds) != expectations["work_kind_count"]:
        raise AssertionError("WorkKind count changed without inventory update")
    if len(handlers) != expectations["completed_transition_handler_count"]:
        raise AssertionError("completed handler count changed without inventory update")

    direct_one_count = _call_count(transitions_tree, "_one")
    if direct_one_count != expectations["direct_one_transition_call_count"]:
        raise AssertionError("direct _one transition count changed")
    complete_reason_count = _complete_reason_count(transitions_tree)
    if complete_reason_count != expectations["transition_complete_reason_count"]:
        raise AssertionError("TransitionPlan complete_reason count changed")

    group_kinds = {str(group["source_work_kind"]) for group in groups}
    if group_kinds != work_kinds | EXPECTED_SPECIAL_GROUPS:
        raise AssertionError(
            "route groups do not cover exactly all WorkKinds and helpers: "
            f"{sorted(group_kinds)}"
        )
    _assert_markers(root, groups)
    _assert_semantic_markers(root)

    taxonomy = matrix["route_outcome_taxonomy"]
    allowed_settlements = set(taxonomy)
    branch_ids: set[str] = set()
    terminal_branches = 0
    branch_count = 0
    for group in groups:
        branches = group.get("branches")
        if not isinstance(branches, list) or not branches:
            raise AssertionError(f"route group has no branches: {group['id']}")
        for branch in branches:
            branch_count += 1
            if set(branch) != REQUIRED_BRANCH_FIELDS:
                raise AssertionError(
                    f"unexpected fields for route branch {branch.get('id')}"
                )
            branch_id = branch["id"]
            if branch_id in branch_ids:
                raise AssertionError(f"duplicate route branch ID: {branch_id}")
            branch_ids.add(branch_id)
            for name in ("trigger", "next", "obligation"):
                if not isinstance(branch[name], str) or not branch[name].strip():
                    raise AssertionError(f"empty {name} in {branch_id}")
            if branch["outcome_state"] not in allowed_settlements:
                raise AssertionError(f"unknown outcome_state in {branch_id}")
            if not isinstance(branch["terminal_source"], bool):
                raise AssertionError(f"terminal_source must be bool in {branch_id}")
            if (
                branch["terminal_source"]
                and branch["outcome_state"] == "provisional"
            ):
                raise AssertionError(
                    f"terminal route cannot remain provisional: {branch_id}"
                )
            terminal_branches += int(branch["terminal_source"])

    audit = audit_path.read_text(encoding="utf-8")
    for marker in (
        "局部实现缺口，不构成需要返回 `cvpr-goal` 的实质语义冲突",
        "不能支持 H1/H2/H3 Claim",
        "optimizer_episode_id",
        "base_prompt_template_digest",
    ):
        if marker not in audit:
            raise AssertionError(f"semantic audit marker missing: {marker}")

    return {
        "schema_version": "1.0",
        "check_id": "CHECK-STAGE-001-ROUTE-INVENTORY",
        "status": "passed",
        "scope": "development_check_only",
        "work_kind_count": len(work_kinds),
        "handler_count": len(handlers),
        "route_group_count": len(groups),
        "route_branch_count": branch_count,
        "transition_complete_reason_count": complete_reason_count,
        "matrix_sha256": _sha256(matrix_path),
        "semantic_audit_sha256": _sha256(audit_path),
    }


def main() -> None:
    """运行检查，打印并可选保存结构化结果。"""

    args = parse_args()
    root = Path(__file__).resolve().parents[2]
    result = run_check(root)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        output = args.output
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
