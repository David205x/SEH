"""Teacher template manifest 与装配测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from search_harness.evolution.research.roles.loader import load_teacher_agent_spec
from search_harness.evolution.research.resources.base import (
    EvaluationEvidenceStore,
    TeacherResources,
    TrialEvidenceStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
TEMPLATE_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"


class TeacherTemplateLoaderTest(unittest.TestCase):
    def test_shared_assembly_keeps_role_contract_outside_manifest(self) -> None:
        """新 Teacher Template 由调用方绑定 Role，而非在 Manifest 重复声明。"""

        evaluation = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollout.jsonl"),
            summary={},
            cases={},
            rollouts={},
            student_template_root=Path("components"),
            harness_manifest={"harness_id": "student", "tools": [], "extensions": []},
        )
        spec = load_teacher_agent_spec(
            TEMPLATE_ROOT / "failure_analyst",
            runtime_context=TeacherResources(evaluation=evaluation),
            role_id="failure_analyst",
            role_version=1,
        )

        manifest_payload = json.loads(
            (TEMPLATE_ROOT / "failure_analyst" / "harness.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("role", manifest_payload)
        self.assertNotIn("output_contract", manifest_payload)
        self.assertNotIn("evolution_policy", json.dumps(manifest_payload))
        self.assertEqual(spec.role.role_id, "failure_analyst")
        self.assertEqual(spec.output.kind, "role_contract")
        self.assertEqual(len(spec.tools.tools), 6)

    def test_loads_all_initial_role_templates(self) -> None:
        """验证九个 Teacher 角色均从目录解析出正确协议和工具集合。"""

        evaluation = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollout.jsonl"),
            summary={},
            cases={},
            rollouts={},
            student_template_root=Path("components"),
            harness_manifest={"harness_id": "student", "tools": [], "extensions": []},
        )
        trials = TrialEvidenceStore(trials={"trial_001": {}})
        resources = TeacherResources(
            evaluation=evaluation,
            trials=trials,
            intervention=object(),  # type: ignore[arg-type]
            compiler=object(),  # type: ignore[arg-type]
            candidate_review=object(),  # type: ignore[arg-type]
        )

        expected = {
            "failure_analyst": "FailureDirection",
            "hypothesis_researcher": "InterventionHypothesis",
            "trial_reviewer": "TrialReview",
            "evidence_reviewer": "EvidenceReview",
            "mechanism_distiller": "MechanismDistillation",
            "intervention_worker": "InterventionWorkerResult",
            "compiler": "CompilerResult",
            "candidate_reviewer": "CandidateReview",
            "conformance_reviewer": "ConformanceFinding",
        }
        for role_id, output_name in expected.items():
            with self.subTest(role_id=role_id):
                spec = load_teacher_agent_spec(
                    TEMPLATE_ROOT / role_id,
                    runtime_context=resources,
                    role_id=role_id,
                )
                self.assertEqual(spec.role.role_id, role_id)
                self.assertEqual(spec.role.output_type.__name__, output_name)
                self.assertTrue(spec.prompt.instructions)
                if role_id == "compiler":
                    tool_names = {tool.name for tool in spec.tools.tools}
                    self.assertIn("finalize_candidate", tool_names)
                    self.assertIn("query_hook_api", tool_names)
                    self.assertNotIn("list_hook_api_symbols", tool_names)
                    self.assertNotIn("get_hook_authoring_guide", tool_names)

    def test_loader_rejects_unknown_external_role(self) -> None:
        """Role 选择由调用方负责，未知 Role 在装配前 fail fast。"""

        with self.assertRaisesRegex(ValueError, "unknown Teacher role"):
            load_teacher_agent_spec(
                TEMPLATE_ROOT / "failure_analyst",
                runtime_context=TeacherResources(),
                role_id="unknown_role",
            )


if __name__ == "__main__":
    unittest.main()
