import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.evolution import (
    ActorCapabilityProfile,
    CapabilityObservation,
    EvaluationContract,
    EvidenceObligation,
    EvolutionResearchStore,
    IterationProduct,
)


class EvolutionResearchStoreTest(TestCase):
    """验证证据驱动研究记录的持久化约束。"""

    def test_persists_capability_contract_and_iteration_product(self) -> None:
        """验证能力画像、评估契约和迭代产物分别持久化。"""

        with TemporaryDirectory(dir=Path.cwd()) as directory:
            store = EvolutionResearchStore(Path(directory) / "research")
            store.record_capability_profile(
                ActorCapabilityProfile(
                    profile_id="student_v1",
                    actor_model="student:model",
                    harness_digest="digest",
                    observations=(
                        CapabilityObservation(
                            capability="follow pre-final feedback",
                            status="supported",
                            observation="2/2 branches continued.",
                            evidence_refs=("trial_1", "trial_2"),
                        ),
                    ),
                    evidence_refs=("review_1",),
                )
            )
            store.record_evaluation_contract(
                EvaluationContract(
                    contract_id="contract_1",
                    hypothesis_ref="hypothesis_1",
                    core_metrics=("accuracy",),
                    mechanism_metrics=("activation_rate",),
                    expected_effect="More evidence-backed answers.",
                    falsifier="Only tool-call count increases.",
                    replicate_count=3,
                    sample_scope="supported failures",
                )
            )
            product_record = IterationProduct(
                iteration=1,
                kind="evidence_recorded",
                summary="Actor follows the intervention.",
                artifact_refs=("trial_1",),
            )
            store.record_iteration_product(product_record)
            store.record_iteration_product(product_record)

            product_lines = (
                (store.root / "iteration_products.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            product = json.loads(product_lines[0])

        self.assertEqual(len(product_lines), 1)
        self.assertEqual(product["kind"], "evidence_recorded")
        self.assertEqual(product["iteration"], 1)

    def test_obligation_queue_keeps_latest_state(self) -> None:
        """验证证据义务以追加事件关闭，并只返回仍开放的条目。"""

        with TemporaryDirectory(dir=Path.cwd()) as directory:
            store = EvolutionResearchStore(Path(directory) / "research")
            store.open_obligation(
                EvidenceObligation(
                    obligation_id="obligation_1",
                    hypothesis_ref="hypothesis_1",
                    question="Does the Actor adopt topk=5?",
                )
            )
            self.assertEqual(len(store.list_open_obligations()), 1)

            resolved = store.resolve_obligation(
                "obligation_1",
                status="satisfied",
                resolution="All three replicates used topk=5.",
                evidence_refs=("trial_1", "trial_2", "trial_3"),
            )

            self.assertEqual(resolved.status, "satisfied")
            self.assertEqual(store.list_open_obligations(), ())

    def test_rejects_duplicate_record_ids(self) -> None:
        """验证稳定 ID 不能被静默覆盖。"""

        with TemporaryDirectory(dir=Path.cwd()) as directory:
            store = EvolutionResearchStore(Path(directory) / "research")
            contract = EvaluationContract(
                contract_id="contract_1",
                hypothesis_ref="hypothesis_1",
                core_metrics=("accuracy",),
                mechanism_metrics=("activation_rate",),
                expected_effect="Improve evidence coverage.",
                falsifier="Coverage does not improve.",
                replicate_count=1,
                sample_scope="one paired case",
            )
            store.record_evaluation_contract(contract)

            with self.assertRaisesRegex(ValueError, "duplicate contract_id"):
                store.record_evaluation_contract(contract)
