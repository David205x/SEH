"""Tests for split Capability and Direction Summarization Passes."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from search_harness.evolution.research.experience_summary import (
    CapabilityEvidenceRecord,
    ExperienceDetail,
    ExperienceDetailStore,
    build_conformance_capability_request,
    build_hook_feasibility_capability_request,
    build_promotion_direction_request,
    make_capability_request,
    materialize_capability_experience_product,
)
from search_harness.evolution.research.roles.contracts import (
    CapabilityExperienceSummary,
    CapabilityObservation,
    DirectionSummary,
    ExperienceValidity,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _observation(observation_id: int = 1) -> CapabilityObservation:
    return CapabilityObservation(
        observation_id=observation_id,
        decision_scope=(
            "Determine whether the visible search history leaves one named "
            "comparison entity uncovered."
        ),
        subject="Hook model classifying one frozen predicate",
        expected="negative",
        observed="positive twice",
        comparison="Same valid input repeated twice.",
        conditions="thinking_mode=disabled; phase=pre_final",
        validity=ExperienceValidity(
            reference="confirmed",
            model_input="confirmed",
            implementation_fidelity="confirmed",
            data_environment="not_applicable",
        ),
        evidence_structure="Two paired repetitions on the same input.",
        open_checks=[],
    )


class ExperiencePacketTest(unittest.TestCase):
    def _request(self, details: list[ExperienceDetail]):
        return make_capability_request(
            observations=[_observation()],
            details=details,
            source_processing_context="A repeated direct model probe completed.",
            observation_sources={1: ["probe"]},
            capability_evidence={
                1: CapabilityEvidenceRecord(
                    expected_decision="negative",
                    observed_by_condition={
                        "disabled": ["positive", "positive"]
                    },
                )
            },
        )

    def test_more_than_three_distinct_detail_reads_are_allowed(self) -> None:
        details = [
            ExperienceDetail(
                detail_id=index,
                observation_id=1,
                resolves=f"check_{index}",
                coverage="complete",
                description=f"Detail {index}",
                content=f"content {index}",
                source_refs=["probe"],
            )
            for index in range(1, 5)
        ]
        request = self._request(details)
        store = ExperienceDetailStore(request.resources)
        store.bind(request.role_input)

        results = [store.inspect(index) for index in range(1, 5)]

        self.assertEqual(len(results), 4)
        self.assertIn("Coverage: complete", results[0])

    def test_repeat_detail_read_is_rejected(self) -> None:
        detail = ExperienceDetail(
            detail_id=1,
            observation_id=1,
            resolves="input_validity",
            coverage="bounded_projection",
            description="Model-visible input projection.",
            content="visible input",
        )
        request = self._request([detail])
        store = ExperienceDetailStore(request.resources)
        store.bind(request.role_input)
        store.inspect(1)

        with self.assertRaisesRegex(ValueError, "already read"):
            store.inspect(1)

    def test_output_refs_must_name_packet_observations(self) -> None:
        request = self._request([])
        store = ExperienceDetailStore(request.resources)
        store.bind(request.role_input)
        good = CapabilityExperienceSummary.model_validate(
            {"items": [{
                "observed_limitation": "mislabels valid negatives positive",
                "evidence_refs": [1],
            }]}
        )
        store.validate_capability_output(good)
        bad = CapabilityExperienceSummary.model_validate(
            {"items": [{
                "observed_limitation": "mislabels valid negatives positive",
                "evidence_refs": [2],
            }]}
        )
        with self.assertRaisesRegex(ValueError, "unknown observations"):
            store.validate_capability_output(bad)

    def test_capability_product_uses_program_scope_and_evidence(self) -> None:
        request = self._request([])
        summary = CapabilityExperienceSummary.model_validate(
            {
                "items": [
                    {
                        "observed_limitation": (
                            "Cannot reliably exclude single-entity facts."
                        ),
                        "evidence_refs": [1],
                    }
                ]
            }
        )

        product = materialize_capability_experience_product(
            request,
            summary,
        )

        self.assertEqual(
            product.items[0].decision_scope,
            request.role_input.observations[0].decision_scope,
        )
        self.assertEqual(
            product.items[0].evidence_summary,
            (
                "thinking disabled: the expected-negative input was "
                "repeatedly labeled positive."
            ),
        )
        self.assertEqual(product.items[0].evidence_refs, ["probe"])

    def test_capability_proposal_rejects_removed_fields(self) -> None:
        with self.assertRaises(ValueError):
            CapabilityExperienceSummary.model_validate(
                {
                    "items": [
                        {
                            "evaluated_behavior": "old model-owned scope",
                            "observed_limitation": "one limitation",
                            "conditions": "old model-owned conditions",
                            "evidence_refs": [1],
                        }
                    ]
                }
            )

    def test_capability_product_rejects_mixed_decision_scopes(self) -> None:
        request = make_capability_request(
            observations=[
                _observation(1),
                _observation(2).model_copy(
                    update={"decision_scope": "A different decision."}
                ),
            ],
            details=[],
            source_processing_context="Two direct probes completed.",
            observation_sources={1: ["probe#1"], 2: ["probe#2"]},
            capability_evidence={
                1: CapabilityEvidenceRecord(
                    expected_decision="negative",
                    observed_by_condition={"disabled": ["positive"]},
                ),
                2: CapabilityEvidenceRecord(
                    expected_decision="negative",
                    observed_by_condition={"disabled": ["positive"]},
                ),
            },
        )
        summary = CapabilityExperienceSummary.model_validate(
            {
                "items": [
                    {
                        "observed_limitation": "one mixed limitation",
                        "evidence_refs": [1, 2],
                    }
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "one decision scope"):
            materialize_capability_experience_product(request, summary)

    def test_direction_summary_allows_at_most_one_item(self) -> None:
        DirectionSummary.model_validate({"items": []})
        item = {
            "evidence_update": "one update",
            "disposition": "narrow this scheme",
            "revisit_condition": "new matched evidence",
            "applicability": "tested prefixes",
            "evidence_refs": [1],
        }
        with self.assertRaises(ValueError):
            DirectionSummary.model_validate({"items": [item, item]})


class ExperienceSourceAdapterTest(unittest.TestCase):
    def test_real_hook_probe_builds_capability_packet(self) -> None:
        path = (
            PROJECT_ROOT
            / "runs/evolution/20260815_qwen3-8b_hook_feasibility/artifacts"
            / "verify_hook_feasibility-64ddfe9a2a85e492/probe.json"
        )
        if not path.is_file():
            self.skipTest("historical Hook feasibility artifact is unavailable")
        probe = json.loads(path.read_text(encoding="utf-8"))

        request = build_hook_feasibility_capability_request(
            probe,
            source_ref="hook_feasibility_probe",
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(len(request.role_input.observations), 2)
        self.assertGreaterEqual(len(request.role_input.detail_directory), 6)
        self.assertIn(
            "single entity",
            request.role_input.observations[0].expected,
        )
        self.assertIn(
            "completed search query",
            request.role_input.observations[1].expected,
        )
        self.assertEqual(
            request.role_input.observations[0].decision_scope,
            probe["phase_probes"][0]["decision_contract"]["predicate"],
        )
        summary = CapabilityExperienceSummary.model_validate(
            {
                "items": [
                    {
                        "observed_limitation": "one supported limitation",
                        "evidence_refs": [1, 2],
                    }
                ]
            }
        )
        product = materialize_capability_experience_product(request, summary)
        self.assertEqual(
            product.items[0].evidence_summary,
            (
                "thinking disabled: both expected-negative inputs were "
                "repeatedly labeled positive. thinking enabled: one input "
                "flipped negative→positive while the other remained negative."
            ),
        )
        self.assertTrue(
            all(
                "#trial_" in refs[0]
                for refs in request.resources.observation_sources.values()
            )
        )

    def test_promotion_builder_targets_mechanism_scheme(self) -> None:
        request = build_promotion_direction_request(
            failure_direction_id="run_g0001_fd0001",
            failure_summary="Student stops before retrieving a missing fact.",
            research_scheme_id="run_g0001_fd0001_rs0001",
            research_summary="Defer final answers when evidence is missing.",
            mechanism_scheme_id="run_g0001_fd0001_rs0001_ms",
            mechanism_summary="One-shot pre-final deferral.",
            mechanism_goal="Increase targeted search before final answer.",
            candidate_review={
                "recommendation": "accept",
                "observed_effect": "Target examples improved without regression.",
                "reason": "Measured effect supports the goal.",
            },
            promotion_gate={"passed": True, "reasons": []},
            source_refs=["candidate_reviewer_artifact"],
        )

        context = request.role_input.direction_context
        self.assertEqual(context.update_target, "mechanism_scheme")
        assert context.mechanism_scheme is not None
        self.assertEqual(
            context.mechanism_scheme.ref,
            "run_g0001_fd0001_rs0001_ms",
        )

    def test_real_conformance_mismatches_build_capability_packet(self) -> None:
        root = (
            PROJECT_ROOT
            / "runs/evolution/20260815_qwen3-8b_fullchain/artifacts"
            / "conformance_checkpoints/8ec0c86505430d20dd952e5f/findings"
        )
        if not root.is_dir():
            self.skipTest("historical Conformance artifacts are unavailable")
        findings = [
            json.loads(path.read_text(encoding="utf-8"))["output"]
            for path in sorted(root.glob("finding_*.json"))
        ]

        request = build_conformance_capability_request(
            findings,
            source_refs=["conformance_findings"],
            mechanism=json.loads(
                (
                    PROJECT_ROOT
                    / "runs/evolution/20260815_qwen3-8b_fullchain/artifacts"
                    / "distill_mechanism-17ff2d1e1dd24b63/mechanism.json"
                ).read_text(encoding="utf-8")
            ),
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(
            request.role_input.observations[0].validity.model_input,
            "confirmed",
        )
        self.assertTrue(
            any(
                item.decision_scope
                == (
                    "any search query in the complete tool-call history "
                    "names the second entity"
                )
                for item in request.role_input.observations
            )
        )
        self.assertTrue(
            any(
                item.decision_scope
                == (
                    "Does the final answer compare two named entities on a "
                    "single attribute while the tool-call history contains "
                    "no search whose query names the second entity, no "
                    "returned passage provides evidence about the second "
                    "entity, and the final answer's stated justification "
                    "treats the second entity's absence from the retrieved "
                    "passages as supporting its comparison conclusion?"
                )
                for item in request.role_input.observations
            )
        )


if __name__ == "__main__":
    unittest.main()
