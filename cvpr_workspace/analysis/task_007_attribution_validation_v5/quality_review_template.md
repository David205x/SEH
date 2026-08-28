# TASK-007 真实归因质量人工审计模板

每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。

## evidence_revise_corpus_confound / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_revise_corpus_confound\run_01.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "One-sided-retrieval hypothesis is inconclusive: trial_004 faithfully issued the required second-entity search for Cia Berg, but the corpus returned no title-count evidence, so the claim that one-sided retrieval causes absence-based comparison errors is unverified (full success 1/2). Continue only if the corpus can supply the required second-entity evidence; otherwise do not rely on the retrieval prompt to fix absence-based errors.", "applicability": "Pre-final deferral retrieval prompts for named-entity comparison tasks where judging the causal effect requires corpus passages containing both entities' evidence; applies to one-shot soft-intervention trials with confirmed implementation fidelity but data-insufficient corpora.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_revise_corpus_confound / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_revise_corpus_confound\run_02.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "The one-sided-retrieval hypothesis (asking the Student to search for the second entity prevents absence-based comparison errors) is inconclusive: trial_004 faithfully issued the query but the corpus returned no title-count evidence, so the success condition was unjudgeable and the absence-based conclusion is not attributable to retrieval direction. Revisit only with a corpus containing the second-entity evidence or a measurable success condition.", "applicability": "Applies to this retrieval-then-judge comparison design (second-entity title-count evidence) where corpus coverage was insufficient; does not extend to corpora containing the required evidence, where the retrieval-direction mechanism remains untested.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_revise_corpus_confound / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_revise_corpus_confound\run_03.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "The one-shot pre-final second-entity search ran faithfully (trial_004 queried Cia Berg), but returned passages lacked the title-count evidence the success condition required, so 'one-sided retrieval causes absence-based comparison errors' remains untested. Disposition: inconclusive; revisit only with trials whose retrieved corpus actually contains the second-entity evidence, or split success into search fidelity versus evidence availability.", "applicability": "Scope: one-shot pre-final second-entity search and the absence-based comparison hypothesis on this corpus. Recheck when retrieved passages contain the required second-entity evidence, or when search fidelity is judged independently of corpus evidence availability.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_reject_no_differential_effect\run_01.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Inserting generic verification context does not cause a follow-up search before finalization: 3 of 4 faithful positive activations finalized without one, the only search success also occurred in the untreated source control, and the treated branch produced no differential action-type effect. Stop unchanged for this mechanism class; revisit only with a redesigned trigger whose search outcomes are attributed to the intervention rather than to control behavior.", "applicability": "Applies to the generic inserted-verification-block mechanism on positive activations before finalization, evaluated by differential action-type effect against a matched source control. Recheck requires a trigger design with search effect activation-attributed and absent from controls.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_reject_no_differential_effect\run_02.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Inserting a generic verification block on faithful positive activations does not cause a follow-up search before finalization: three of four activations finalized without one, the sole search success also occurred in its untreated source control, and the treated branch showed no differential action-type effect. Stop unchanged. Revisit only with a mechanism showing activation-attributed search beyond control and an explicit trigger predicate.", "applicability": "Scope: the generic verification-context soft intervention on faithful positive activations in this task/decision setting; missing negative-stratum coverage is not causal. Recheck applies to refined context interventions tested against matched controls with explicit success predicates.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_reject_no_differential_effect\run_03.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Inserting a generic verification block into faithful positive activations does not cause a follow-up search before finalization: 3 of 4 activations finalized without one, and the sole search success also occurred in the untreated source control, so the treated branch shows no differential action-type effect. Stop this mechanism unchanged.", "applicability": "Verification-context insertion intended to trigger follow-up search before finalization in this task setting; revisit only with a redesigned mechanism demonstrating a differential effect against matched controls.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_reject_harmful_overtrigger\run_01.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "Generic evidence-gap patch to induce follow-up search is rejected unchanged: of two faithful positive activations only one triggered the intended search, while a complete-evidence case over-triggered and changed a correct answer to wrong, showing no selectivity. Revisit only if a redesigned trigger with explicit-negative guarding demonstrates matched-control benefit and avoids harm on complete evidence.", "applicability": "Generic evidence-gap patch interventions meant to induce follow-up search in evidence-review/trial pipelines, on the tested positive and complete-evidence case types; recheck only with a selective mechanism proven against explicit negatives.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_reject_harmful_overtrigger\run_02.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "Generic evidence-gap patch as a follow-up-search trigger is not viable: across two faithful activations it missed the intended positive (clean falsifier immediately finalized wrong) and over-triggered on complete evidence, changing a correct answer to wrong. Disposition: stop unchanged; revisit only with a trigger shown selective on explicit-gap versus complete-evidence matched cases.", "applicability": "Generic evidence-gap patch triggers for follow-up search under faithful activation with complete coverage; do not reuse until selectivity on both explicit-gap and complete-evidence cases is demonstrated with matched controls.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\evidence_reject_harmful_overtrigger\run_03.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "Generic evidence-gap patch rejected unchanged: faithfully applied in both decisive trials, it missed an intended positive (clean falsifier immediately finalized wrong) and over-triggered on complete evidence, changing a correct answer to wrong. The paired miss and harmful over-trigger contradict the direction's claimed selectivity; stop unchanged and require a selective trigger for any revisit.", "applicability": "Generic evidence-gap soft interventions intended to induce follow-up search, evaluated in faithful activation trials with complete default coverage; revisit only with a trigger shown to fire on genuine gaps while leaving complete-evidence decisions untouched.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\hook_feasibility_student_instability\run_01.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Frozen Hook model: with thinking disabled, both valid explicit-negative cases (one-sided two-entity gaps) were repeatedly labeled positive; with thinking enabled, one identical negative flipped across repetitions. The explicit-negative boundary is narrow and unstable, so Hypothesis Researcher must not rely on it unchanged—revise evidence scope or add a deterministic negative guard.", "applicability": "Only the frozen Hook three-way evaluator on real-prefix, parse-clean one-sided evidence-gap negatives in both thinking modes. Recheck if the decision contract, input scope, or model changes, or after a deterministic guard is added.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\hook_feasibility_student_instability\run_02.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Frozen Hook model cannot reliably realize the explicit-negative boundary of the three-label one-sided two-entity-gap evaluator: both explicit negatives were repeatedly labeled positive with thinking disabled, one identical negative flipped with thinking enabled, and positives stayed stable and parse-clean. Do not rely unchanged: add a deterministic guard or run a fixed-mode repeated negative recheck.", "applicability": "Frozen Hook three-way decision over real-prefix one-sided two-entity evidence-gap cases in both probed thinking modes. Limit may release only if a fixed-mode repeated probe stably labels both explicit negatives correctly.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\hook_feasibility_student_instability\run_03.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "The frozen Hook evaluator mislabels explicit negatives under the three-way decision contract: with thinking disabled, both valid negative real-prefix cases were positive on every repetition; with thinking enabled, one identical negative flipped across repetitions. Its explicit-negative boundary is neither selective nor stable. Hypothesis Researcher must not rely unchanged on the Hook negative verdict; add a deterministic guard or a specified recheck.", "applicability": "Applies only to the frozen Hook model's three-way decision on one-sided two-entity real-prefix cases with explicit negatives; the boundary may be released or rechecked under the same decision contract by a deterministic guard or a specified recheck.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\distiller_not_distillable_model_boundary\run_01.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen Hook model cannot realize the validated activation contract's required negative boundary: it mislabeled the both-entities-queried negative in 4/4 parse-clean probes across two contract wordings and also a valid single-entity negative, with reference, input, and probe fidelity confirmed. Hypothesis Researcher must not rely unchanged on this Hook evaluator; add a deterministic guard for both-entity negatives or run a specified boundary recheck before reuse.", "applicability": "Applies to this Hook model's decision scope on both-entity and single-entity negatives for the one-sided-search task. Upstream control success does not transfer to deployability; reuse requires a recheck with another permitted model or a corrected boundary specification.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\distiller_not_distillable_model_boundary\run_02.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen Hook model mislabeled valid explicit negatives in 4/4 both-entity-queried probes and also mislabeled a single-entity negative; two contract wordings and parse-clean probe execution rule out parser or wiring defects. The model cannot realize the required negative boundary from the validated activation contract, so Hypothesis Researcher must not rely unchanged on it: add a deterministic guard or run a specified recheck before reusing distillation.", "applicability": "Scope: the permitted Hook model, three-way distillation of the one-sided-search intervention, valid both-entity-queried and single-entity queried negatives. Limit holds until a recheck on equivalent negatives shows reliable separation, or the negative boundary is moved to a deterministic guard.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\distiller_not_distillable_model_boundary\run_03.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen deployable Hook model mislabeled the contract's required both-entity negative in 4/4 probes and also a single-entity negative, despite valid inputs and two contract wordings ruling out parser/wiring defects. The upstream intervention passed controls, so the Hook model cannot realize the required negative rejection boundary. Hypothesis Researcher: do not rely unchanged; add a deterministic guard or recheck.", "applicability": "Applies only to this Hook model's three-way decision on explicit both-entity and single-entity negatives from the validated activation contract. A model change, a revised contract boundary, or a deterministic rejection guard would release the limit.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_empty_passage_projection / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\conformance_empty_passage_projection\run_01.json`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['project actual retrieved passages into classifier', 'do not classify on empty evidence']`
- Forbidden attributions: `['Student semantic capability is established as the cause']`
- Output: `{"items": [{"lesson": "Compiler violated its contract obligation to project the actual retrieved passages: the Candidate's semantic classifier received an empty placeholder while real passages existed in the trajectory, so the semantic decision ignored its declared input (four mismatches). Next action: re-wire projection so the classifier receives the actual retrieved passages; completion check: Candidate classifier input equals the trajectory passages with zero mismatches.", "applicability": "Applies to Compiler implementation of the frozen Mechanism Spec where retrieved-passage runtime inputs must be projected into the Candidate; covers any placeholder substitution for available trajectory data in Candidate wiring.", "evidence_refs": ["conformance"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\conformance_semantic_evaluator_boundary\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "Frozen Hook evaluator cannot selectively implement 'defer only unsupported committed values': with faithful Hook structure and deterministic action wiring, four valid mismatches deferred explicitly grounded values (explicit-link negative boundary) and treated refusals/bare mentions as committed unsupported values (no-committed-value boundary). Repeated two-boundary over-trigger; do not rely unchanged - add a deterministic guard or recheck the defer boundary.", "applicability": "Applies to the Hook evaluator's defer decision on valid committed-answer and evidence-gap inputs under the conformance three-way contract. Releases when a recheck with corrected boundary examples or a deterministic guard eliminates over-deferral on explicit negatives and non-commitments.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\conformance_semantic_evaluator_boundary\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "The frozen Hook evaluator cannot realize 'defer only unsupported committed values': four valid mismatches flagged explicitly grounded values as positive and refusals/bare mentions as committed unsupported values, violating both explicit-link negative and no-committed-value uncertain clauses despite faithful Hook and deterministic wiring. Hypothesis Researcher: do not rely unchanged; add a deterministic guard for explicit negatives and evidence-gap refusals, or recheck on a valid probe.", "applicability": "Scope: Hook-model evaluator on committed-answer/evidence-gap examples in conformance with faithful Hook and deterministic wiring; limit holds for explicit-negative and uncertain clauses. Release only if a valid probe shows discrimination of explicit negatives from positives on both clauses.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\conformance_semantic_evaluator_boundary\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "Frozen Hook-model evaluator cannot realize \"defer only unsupported committed values\": across four valid cases it treated explicitly grounded values as positive (defer) and refusals/bare mentions as committed unsupported values, false-positive on two required boundaries despite faithful structural Hook and deterministic wiring. Do not rely unchanged; revise the three-way decision contract or add a deterministic guard, then recheck.", "applicability": "Hook-model evaluator for committed-value deferral under explicit-link negative and no-committed-value uncertain contract clauses. A revised contract/guard must be re-validated on both boundaries, or a different Hook model re-probed on these cases, before reuse.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_reject_intrinsic_grounding_predicate\run_01.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Strict single-passage grounding gate (a passage must explicitly state the relation before committing), faithfully implemented with conformance passed, yields no net benefit: accuracy +0.6pp, 14 regressions vs 15 improvements, ~5.6x tokens, and correct retrieval-supported answers repeatedly deferred. Stop unchanged as a mandatory withhold gate; revisit only with a selective predicate that avoids deferring supported answers at acceptable cost.", "applicability": "Mandatory single-passage explicit-grounding withhold gates for relation-grounded Q&A over retrieval corpora; excludes soft-signal or multi-passage grounding variants and settings where deferral cost is negligible.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_reject_intrinsic_grounding_predicate\run_02.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The single-passage grounding predicate (require one passage to explicitly state the relation before committing an answer), faithfully conformant and evaluated on the same 225 records, gave no net benefit: +0.6pp accuracy, 14 regressions vs 15 improvements, ~5.6x tokens, higher instability, and repeated deferral of correct retrieval-supported answers. Stop using this predicate unchanged as the answer-commit gate; a legitimate revisit requires evidence that changes this trade-off.", "applicability": "Two-phase withhold/defer mechanism whose commit predicate demands one passage explicitly state the relation, versus incumbent, on 225 records. Revisit only with evidence of materially better deferral precision or a cheaper gate form yielding accuracy gain without the ~5.6x token cost.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_reject_intrinsic_grounding_predicate\run_03.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Single-passage grounding (require one passage to explicitly state the relation before committing) is unsupported: vs the incumbent on 225 records it gained only +0.6pp accuracy with 14 regressions vs 15 improvements, deferred correct retrieval-supported answers, lowered stable-correct, and raised tokens ~5.6x. Disposition: stop unchanged. Revisit only with evidence of differential benefit on genuinely unsupported cases, preserved supported-answer rate, and acceptable cost.", "applicability": "Scope: single-passage grounding / withhold-defer mechanisms for retrieval-supported QA under the frozen Mechanism Spec on this 225-record comparison. A legitimate revisit requires separately measured selectivity on unsupported relations, no deferral of supported answers, and cost near the incumbent.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_reject_hook_false_positive_scope\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Frozen semantic Hook model activated positive on two distinct valid explicit contract-negative questions (joint and single-entity); one caused a direct regression, and no intended positive behavior appeared. Narrow boundary: the Hook's positive decision does not separate genuine one-sided two-candidate evidence gaps from explicit contract negatives. Hypothesis Researcher: do not rely unchanged; add a deterministic explicit-negative guard or run a specified recheck before any use.", "applicability": "Frozen Hook three-way decision on valid real evaluation prefixes with explicit contract-negative joint/single-entity questions. Released if a matched probe shows no positive activation on explicit negatives or a deterministic negative filter precedes Hook activation.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic Hook for detecting genuine one-sided two-candidate evidence gaps: stop unchanged. Faithful runs produced positive activations only on explicit contract-negative questions, no intended positive behavior, no attributed utility (improvements only on Hook-negative no-op runs), accuracy declined, Hook cost rose sharply. Revisit only with a mechanism showing selective activation on genuine gaps with measured utility at acceptable cost.", "applicability": "Applies to semantic-Hook-based gap detection in this two-candidate evaluation setting. It does not cover Hook contracts with explicit negative-rule pre-filtering or other decision scopes; those need their own selectivity and utility evidence.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_reject_hook_false_positive_scope\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Frozen semantic Hook model over-triggers on explicit contract negatives: on two valid evaluation prefixes (a joint and a single-entity explicit-negative question) it emitted positive activations, one causing a direct regression, with no intended positive behavior. It cannot selectively detect genuine one-sided evidence gaps. Hypothesis Researcher: do not rely unchanged; add a deterministic explicit-negative guard or recheck its selectivity before reuse.", "applicability": "Semantic Hook three-way decision on two-candidate evaluation prefixes with explicit contract-negative joint and single-entity questions, faithful Candidate wiring. Recheck after adding an explicit-negative guard or recalibrating the Hook so neither case over-triggers.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook detection of one-sided two-candidate evidence gaps showed no attributed utility: positive activations fell only on explicit contract negatives, improvements came only from Hook-negative no-op runs, accuracy declined and Hook cost rose sharply. Disposition: stop unchanged; revisit only with a variant showing differential positive-case benefit and acceptable cost.", "applicability": "Semantic-Hook evidence-gap detection in two-candidate evaluation on valid prefixes; continue only with separately measured positive-case utility and bounded Hook cost, or a cheaper selective mechanism.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_reject_hook_false_positive_scope\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen semantic Hook model positively activates on explicit contract-negative joint and single-entity questions in two valid evaluation prefixes, one activation causing a direct regression and no intended positive behavior; it does not selectively detect genuine one-sided two-candidate evidence gaps. Do not rely unchanged: add a deterministic explicit-negative guard or recheck Hook selectivity on negatives before reuse.", "applicability": "Applies to the frozen Hook model's decisions on valid evaluation prefixes under the current contract, covering explicit contract-negative joint and single-entity questions. A release/recheck needs valid positive cases with matched negatives showing zero negative activation.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook gating for one-sided two-candidate evidence gaps is not viable as run: every positive activation hit an explicit contract-negative and aggregate evidence shows no attributed utility - gains only on Hook-negative no-op runs, accuracy declined, Hook cost rose sharply. Stop unchanged; revisit only with a design measuring activation-attributed benefit on genuine positives and bounded cost.", "applicability": "Applies to the semantic-Hook soft-intervention class under the current decision contract and evaluation prefixes. A legitimate revisit needs a redesigned mechanism with measured activation-attributed utility, zero explicit-negative activation, and cost-bounded operation.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_no_attributed_utility / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_reject_no_attributed_utility\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['separate activation-attributed utility from no-op variance', 'classifier false positive and cost']`
- Forbidden attributions: `['aggregate improvements prove mechanism benefit']`
- Output: `{"items": [{"lesson": "Defer-to-search Hook lacked utility: of eight activations, every follow-up search produced no new correct answer, activation cases regressed or stayed equal, all improvements came from no-op paths, one definitive answer was falsely deferred, and Hook cost added ~271k tokens. Disposition: stop unchanged; revisit only with a selectivity-gated trigger sparing definitive answers plus matched-control proof that deferral improves accuracy net of cost.", "applicability": "Applies to one-shot Hook deferral of evidence-gap final answers to induce targeted follow-up search in comparable ~75-example evaluations. Not applicable to deterministic guards, validated retrieval-augmentation, or settings where the follow-up search is shown to yield new correct answers.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_selectivity_and_cost / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_reject_selectivity_and_cost\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['selectivity harm offsets target benefit', 'avoid per-event semantic classification cost']`
- Forbidden attributions: `['one successful case justifies adoption']`
- Output: `{"items": [{"lesson": "Second-entity search trigger for count/possession comparisons with one-sided evidence over-fired: Hook classified essentially every search event; one target case improved but an out-of-scope shared-membership false positive regressed a stable-correct case; accuracy flat, consistency/majority-correct declined, regressions exceeded improvements, tokens +93%. Disposition: narrow to proven activation-attributed benefit/selectivity; revisit only with matched-control net accuracy gain at bounded cost.", "applicability": "Count/possession comparisons with one-sided evidence; Hook-mediated semantic triggering of second-entity search; candidate-review evaluation with activation attribution and regression/cost balance.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_validation_unchanged_compiler_work / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v5\runs\candidate_validation_unchanged_compiler_work\run_01.json`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['change the implementation before resubmission', 'fix coverage and defer action together']`
- Forbidden attributions: `['Candidate Validator error', 'Student capability failure']`
- Output: `{"items": [{"lesson": "Compiler resubmitted the Candidate unchanged, retaining both deterministic defects (first-entity-only query labeled as covering both entities; no exactly-one defer with feedback) despite carrying the prior validation obligations. Consequence: validation rejected the resubmission; the attempt starts anew. Next: implement the query-coverage and one-shot-deferral fixes before resubmitting; completion when validation no longer reports the unchanged rejected candidate.", "applicability": "Applies to Compiler resubmissions in the candidate_validation revision loop: resubmitting an unchanged artifact that carries prior validation obligations is a Compiler work failure, not evidence about the research direction or the frozen Student model, and it exhausts the compile-retry budget.", "evidence_refs": ["validation"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## Anchor 稳定性

- `evidence_revise_corpus_confound`: type_sets=`[['experiment_direction'], ['experiment_direction'], ['experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `evidence_reject_no_differential_effect`: type_sets=`[['experiment_direction'], ['experiment_direction'], ['experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `evidence_reject_harmful_overtrigger`: type_sets=`[['experiment_direction'], ['experiment_direction'], ['experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `hook_feasibility_student_instability`: type_sets=`[['student_capability'], ['student_capability'], ['student_capability']]`, type_stable=`True`; semantic stability: TODO
- `distiller_not_distillable_model_boundary`: type_sets=`[['student_capability'], ['student_capability'], ['student_capability']]`, type_stable=`True`; semantic stability: TODO
- `conformance_semantic_evaluator_boundary`: type_sets=`[['student_capability'], ['student_capability'], ['student_capability']]`, type_stable=`True`; semantic stability: TODO
- `candidate_reject_intrinsic_grounding_predicate`: type_sets=`[['experiment_direction'], ['experiment_direction'], ['experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `candidate_reject_hook_false_positive_scope`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`True`; semantic stability: TODO
