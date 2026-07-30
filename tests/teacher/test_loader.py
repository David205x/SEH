"""Teacher template manifest 与装配测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from search_harness.teacher.loader import load_teacher_agent_spec
from search_harness.teacher.manifest import load_teacher_manifest
from search_harness.teacher.resources import (
    EvaluationEvidenceStore,
    TeacherResources,
    TrialEvidenceStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"


class TeacherTemplateLoaderTest(unittest.TestCase):
    def test_loads_all_initial_role_templates(self) -> None:
        """验证八个 Teacher 角色均从目录解析出正确协议和工具集合。"""

        evaluation = EvaluationEvidenceStore(
            report_dir=Path("report"),
            rollout_file=Path("rollout.jsonl"),
            summary={},
            cases={},
            rollouts={},
            actor_plugins_root=Path("plugins"),
            harness_manifest={"harness_id": "actor", "tools": [], "extensions": []},
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
        }
        for role_id, output_name in expected.items():
            with self.subTest(role_id=role_id):
                spec = load_teacher_agent_spec(
                    TEMPLATE_ROOT / role_id / "plugins",
                    runtime_context=resources,
                )
                self.assertEqual(spec.role.role_id, role_id)
                self.assertEqual(spec.role.output_type.__name__, output_name)
                self.assertTrue(spec.prompt.instructions)
                if role_id == "compiler":
                    tool_names = {tool.name for tool in spec.tools.tools}
                    self.assertIn("finalize_candidate", tool_names)
                    self.assertNotIn("list_hook_api_symbols", tool_names)
                    self.assertNotIn("query_hook_api", tool_names)

    def test_manifest_rejects_extensions(self) -> None:
        """验证 Teacher template 不会静默忽略未实现的 extension 声明。"""

        payload = {
            "schema_version": 1,
            "harness_id": "invalid",
            "role": {"id": "failure_analyst", "version": 1},
            "output_contract": {"id": "failure_direction", "version": 1},
            "tools": [],
            "prompt": {
                "instance_id": "prompt",
                "entrypoint": "prompt.py:build",
                "config": {},
                "evolution_policy": "fixed",
            },
            "extensions": [
                {
                    "instance_id": "hook",
                    "entrypoint": "hook.py:build",
                    "config": {},
                    "evolution_policy": "fixed",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "harness.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "do not support extensions"):
                load_teacher_manifest(root)

    def test_loader_rejects_output_contract_mismatch(self) -> None:
        """验证模板不能为固定角色替换成不匹配的模型输出协议。"""

        payload = {
            "schema_version": 1,
            "harness_id": "invalid",
            "role": {"id": "failure_analyst", "version": 1},
            "output_contract": {"id": "evidence_review", "version": 1},
            "tools": [],
            "prompt": {
                "instance_id": "prompt",
                "entrypoint": "prompt.py:build",
                "config": {},
                "evolution_policy": "fixed",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "harness.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "output contract mismatch"):
                load_teacher_agent_spec(
                    root,
                    runtime_context=TeacherResources(),
                )


if __name__ == "__main__":
    unittest.main()
