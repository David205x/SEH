# TASK-007 真实归因质量人工审计模板

每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。

## evidence_revise_corpus_confound / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\evidence_revise_corpus_confound\run_01.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Actual types: `['teacher_work', 'experiment_direction']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "Revise the hypothesis: one-sided retrieval is not the cause of the absence-based error. In trial_004 the deferral faithfully triggered a Cia Berg query, yet the five returned passages contained no title-count or induction evidence and the revised final again reasoned from absence. Attribute the error to unverified corpus sufficiency for the second entity (which the hypothesis itself flagged as an unverified obligation), not to retrieval sidedness.", "applicability": "When the success condition requires citing retrieved evidence for both named entities but corpus sufficiency for the second entity was never verified before attributing the failure to retrieval behavior.", "evidence_refs": ["review"]}, {"experience_type": "experiment_direction", "lesson": "Before testing hypotheses that contrast one-sided vs two-sided retrieval as causes of absence-based comparison errors, verify that title-count or induction evidence for both entities actually exists in the corpus and is retrievable; otherwise absence reasoning is a data-sufficiency artifact and cannot distinguish retrieval-side causes.", "applicability": "When designing experiments whose hypothesis implicates retrieval sidedness in absence-based comparison errors and the corpus coverage for the target entities is unverified.", "evidence_refs": ["review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_revise_corpus_confound / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\evidence_revise_corpus_confound\run_02.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Actual types: `['teacher_work']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "The hypothesis set a success condition requiring cited retrieved evidence for both named entities while its own special obligation flagged corpus sufficiency for the unqueried entity as unverified; trial_004's faithful follow-up query for Cia Berg returned five passages with no title-count evidence and the final again used absence reasoning, so the error source is an unsatisfiable success condition, not one-sided retrieval. Verify corpus sufficiency for every entity a comparison hypothesis names before finalizing it, or relax the success condition to match retrievable evidence.", "applicability": "Applies when designing a comparison hypothesis that will be scored on citing retrieved evidence for each named entity, especially when corpus sufficiency for one entity is already flagged as unverified.", "evidence_refs": ["review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_revise_corpus_confound / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\evidence_revise_corpus_confound\run_03.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Actual types: `['experiment_direction']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "A trial whose follow-up query for the second entity returns passages with no title-count or induction evidence cannot demonstrate absence-based comparison errors: the corpus lacked the evidence, so absence reasoning was confounded with a retrieval/environment gap and may even be correct. Design evaluations to verify corpus sufficiency for both comparison entities (e.g., seed retrievable title-count evidence for each) before scoring absence-based conclusions as failures, and mark trials where the flagged sufficiency remains unverified as inconclusive rather than as Student errors.", "applicability": "Applies to evaluating absence-based comparison conclusions when the hypothesis or success condition flags corpus sufficiency for a target entity as unverified, and when scoring relies on retrieved title-count evidence for both named entities.", "evidence_refs": ["review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\evidence_reject_no_differential_effect\run_01.json`
- Expected primary layers: `['upstream_design']`
- Actual types: `['student_capability']`
- Tool views: `['decision_trace', 'decision_trace']`; successful: `['decision_trace', 'decision_trace']`; failed calls: `0`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"experience_type": "student_capability", "lesson": "With faithful insertion of a generic verification block on positive activations (no leakage or runtime failure), the model finalized without a follow-up search in 3/4 trials, the fourth search also occurred in the untreated source control, and an entity-identity-confound trial also finalized without verification; inserted verification context thus produced no differential action-type effect and does not reliably trigger a follow-up search. Do not treat verification-context insertion as a follow-up-search trigger; any proposed trigger must show a differential effect vs. its untreated control.", "applicability": "Applies to experiments that insert generic verification context into positive activations expecting it to cause a follow-up search before finalization, and to any mechanism whose effect is judged by comparing against an untreated source control.", "evidence_refs": ["review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\evidence_reject_harmful_overtrigger\run_01.json`
- Expected primary layers: `['upstream_design']`
- Actual types: `[]`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `null`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\hook_feasibility_student_instability\run_01.json`
- Expected primary layers: `['student_capability']`
- Actual types: `['teacher_work']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "Make the evaluator's negative branch mode-independent and deterministic: the decision contract says single-entity factoids are negative, yet the hook labeled both single-entity negative trials positive when thinking_mode was disabled and flipped the identical trial_002 negative-to-positive across repetitions when enabled. Enforce the negative rule before any mode-dependent branch and require identical inputs to yield identical labels.", "applicability": "When realizing the three-label evaluator for one-sided two-entity evidence gaps, apply whenever the negative-labeling branch is conditioned on runtime mode and repeated identical inputs must be stable across thinking modes and repetitions.", "evidence_refs": ["hook_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\hook_feasibility_student_instability\run_02.json`
- Expected primary layers: `['student_capability']`
- Actual types: `['student_capability']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"experience_type": "student_capability", "lesson": "With an adequate contract (single-entity factoids are negative) and parse-clean outputs, the frozen three-label evaluator fails to stably and correctly label one-sided single-entity negatives: thinking_mode disabled labeled both repeated negative trials positive, and thinking_mode enabled flipped identical trial_002 negative-to-positive across repetitions while positive trials stayed correct. This repeated pattern is a model capability/stability boundary for one-sided two-entity gap discrimination; single-run pass rates (7/8) must not be treated as deterministic evidence of feasibility.", "applicability": "Applies when probing a frozen three-label evaluator for one-sided two-entity evidence gaps: whenever identical real-prefix cases are re-run or thinking mode is toggled, single-entity negative labels are not stable and need a decision procedure that absorbs label variance before any feasibility claim.", "evidence_refs": ["hook_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\hook_feasibility_student_instability\run_03.json`
- Expected primary layers: `['student_capability']`
- Actual types: `['teacher_work']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "Revise the evaluator-realization hypothesis: the frozen evaluator is not feasible as realized because it violates the unambiguous decision contract that single-entity factoids are negative (with thinking_mode disabled, both repetitions of negative trials _002/_003 were labeled positive; with thinking_mode enabled, identical trial_002 flipped negative→positive). Require a deterministic, contract-conformant labeling procedure and treat any inter-run flip or contract-violating label on negatives as blocking instead of accepting 7/8 reference-correct as a feasibility signal.", "applicability": "When realizing a three-label evaluator for one-sided two-entity evidence gaps from a frozen probe and judging feasibility; applies whenever labels must be stable across identical inputs and conform to the decision contract on single-entity negatives.", "evidence_refs": ["hook_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\distiller_not_distillable_model_boundary\run_01.json`
- Expected primary layers: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"experience_type": "student_capability", "lesson": "The hook-model evaluator cannot realize the required one-sided-search semantic boundary: when both entities were already queried, a query naming both entities must be treated as non-intervention, yet the production model asserted the query named only the first entity and returned positive in 4/4 generations across two contract wordings (and mislabeled the single-entity negative in 2/2 under one wording). Treat this negative class as beyond this evaluator's capability and do not deploy it without a model that can realize the boundary.", "applicability": "Applies when distilling a validated intervention into a fixed hook evaluator whose activation contract requires distinguishing negatives where both entities were already queried.", "evidence_refs": ["distillation"]}, {"experience_type": "experiment_direction", "lesson": "Make the upstream contract's required semantic-boundary negatives (both-entities-queried non-intervention) mandatory acceptance probes in the distillation pipeline: passing the intervention's 2 positive and 2 negative controls did not predict whether the distilled evaluator could realize the boundary, and repeated failure persisted even after contract wording was varied.", "applicability": "Applies to any distillation into a weaker hook evaluator where the activation condition defines negative cases the student model may not discriminate.", "evidence_refs": ["distillation"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_activation_budget_implementation / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_activation_budget_implementation\run_01.json`
- Expected primary layers: `['implementation']`
- Actual types: `['teacher_work']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['enforce rollout-local activation budget', 'Compiler implementation assumption failed']`
- Forbidden attributions: `['Conformance Reviewer error', 'Student capability failure']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "When compiling the one-shot pre-final deferral, enforce the declared rollout-local pre_final activation budget inside the produced artifact instead of relying on the runtime phase activation budget; conformance finding_002 observed deferrals continuing after the declared pre_final activation budget was exhausted because the Candidate used the runtime phase budget as the enforcement point. Emit code that checks the declared rollout-local limit directly, with a strict activation budget compiled in at build time.", "applicability": "Applies whenever the compiler emits one-shot pre-final deferral logic and the upstream contract declares a rollout-local pre_final activation budget that conformance checks subsequently verify.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_activation_budget_implementation / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_activation_budget_implementation\run_02.json`
- Expected primary layers: `['implementation']`
- Actual types: `['teacher_work']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['enforce rollout-local activation budget', 'Compiler implementation assumption failed']`
- Forbidden attributions: `['Conformance Reviewer error', 'Student capability failure']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "The compiler must emit the one-shot pre-final deferral with the declared rollout-local pre_final activation budget as a hard, compiled-in bound; delegating enforcement to the runtime phase activation budget let deferrals continue after the declared budget was exhausted (finding_002), even though the other two conformance findings were faithful.", "applicability": "Applies whenever the compiler targets a one-shot pre-final deferral whose contract declares a strict rollout-local pre_final activation budget and the compiled candidate could otherwise fall back on a looser runtime phase budget.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_activation_budget_implementation / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_activation_budget_implementation\run_03.json`
- Expected primary layers: `['implementation']`
- Actual types: `['teacher_work']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['enforce rollout-local activation budget', 'Compiler implementation assumption failed']`
- Forbidden attributions: `['Conformance Reviewer error', 'Student capability failure']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "Compiler must generate candidates that enforce the declared pre_final activation budget as a hard rollout-local limit; the candidate kept deferring after that budget was exhausted because it relied on the runtime phase activation budget instead of the declared limit.", "applicability": "Applies when compiling one-shot pre-final deferral candidates that declare a strict activation budget; the limit enforced by the compiled artifact must match the declared budget and cap further deferrals once exhausted.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_empty_passage_projection / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_empty_passage_projection\run_01.json`
- Expected primary layers: `['implementation']`
- Actual types: `['teacher_work']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['project actual retrieved passages into classifier', 'do not classify on empty evidence']`
- Forbidden attributions: `['Student semantic capability is established as the cause']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "Repair the candidate's data flow so the semantic classifier is invoked with the actual retrieved passages projected from the contract's declared retrieved-passage input; the four mismatches showed the classifier received an empty passage list, so its relation-grounding decision ignored the required input.", "applicability": "Applies when a conformance.revise_implementation repair targets a classifier decision that must ground the requested relation on retrieved passages and the mismatch trace shows an empty passage list at call time.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_positive_action_not_applied / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_positive_action_not_applied\run_01.json`
- Expected primary layers: `['implementation']`
- Actual types: `['teacher_work']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['wire positive decision to required defer action', 'update feedback and consumed state']`
- Forbidden attributions: `['upstream evidence design failure']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "When the positive pre-final condition holds, the compiler must apply the full defer path: execute the required defer action, append the verification-note feedback, and set the consumed flag; passing the candidate through with no Hook changes leaves an unsupported final candidate and produces a conformance mismatch.", "applicability": "Applies to compiler implementations of the conformance contract whenever a candidate reaches the positive pre-final condition and must be deferred after the verification note is inserted.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_semantic_evaluator_boundary\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['student_capability', 'teacher_work']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"experience_type": "student_capability", "lesson": "A Hook-model evaluator does not stably hold the explicit negative and uncertain conformance boundaries: across four mismatches it inappropriately deferred both passages that explicitly ground the committed value (contract: pass-through) and evidence-gap refusals or bare mentions with no committed value (contract: no-op), so its classification of explicit-link negatives, uncertainties, and unsupported commitments is unreliable.", "applicability": "When a Hook-model evaluator decides deferral of a committed value under a contract that explicitly separates explicit-link negatives (pass-through), refusal/evidence-gap uncertainties (no-op), and ungrounded positives (defer).", "evidence_refs": ["conformance"]}, {"experience_type": "teacher_work", "lesson": "When distilling the mechanism, guard the negative and uncertain boundaries deterministically (explicit-link passage -> pass-through; refusal, evidence-gap, or no committed value -> no-op) and consult the Hook-model evaluator only for genuine positives (a committed value lacking the required passage link), so deferral applies solely to truly unsupported committed values rather than the model's judgment on the boundary cases.", "applicability": "When revising the mechanism that routes committed values through a Hook-model evaluator for conformance, given that the wiring was faithful but the evaluator crossed both explicit-link negative and no-committed-value uncertain boundaries.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_semantic_evaluator_boundary\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['student_capability']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"experience_type": "student_capability", "lesson": "With an adequate decision contract (explicit-link negative → pass through; refusal/evidence-gap/no committed value → no-op; committed value lacking a link → defer) and a structurally faithful Hook, the learned Hook-model evaluator repeatedly (4/4 mismatches) treated explicit-link passages as positives and no-committed-value refusals or bare mentions as committed values, causing inappropriate deferral; deferral decisions must therefore be checked against the deterministic contract rules or the evaluator's decision space constrained.", "applicability": "Applies when a Hook-model evaluator decides whether to defer a committed value under a contract with explicit negative/uncertain/positive categories whose discriminators are passage-link existence and committed-value presence; boundary accuracy on these categorical rules is the binding constraint.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_semantic_evaluator_boundary\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['student_capability', 'teacher_work']`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"experience_type": "student_capability", "lesson": "With an explicit decision_contract (explicit-link passage → pass through; refusal, evidence-gap, or no committed value → no-op; only a committed value lacking the required link → defer), a structurally faithful Hook, and deterministic action wiring present, the Hook-model still crossed both the explicit-link negative and the no-committed-value uncertain boundaries across four mismatches and deferred inappropriately. Model judgment cannot be relied on to apply these boundary rules reliably.", "applicability": "Applies when a model-based Hook evaluator judges conformance of committed values under explicit negative/uncertain/positive rules; expect over-deferral on explicit-link negatives and on refusals or bare mentions unless those boundaries are guarded.", "evidence_refs": ["conformance"]}, {"experience_type": "teacher_work", "lesson": "Revise the Hook-model evaluator so deferral fires only for the positive case (a specific committed value lacking the required passage link) and never for explicit-link negatives or no-committed-value uncertains; add deterministic guards that detect explicit passage links and refusal/evidence-gap/no-value statements and override model classification before any deferral decision.", "applicability": "Applies when building or repairing the conformance Hook-model evaluator under a decision_contract that already defines explicit negative and uncertain boundary rules.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_query_coverage_projection / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_query_coverage_projection\run_01.json`
- Expected primary layers: `['implementation']`
- Actual types: `['teacher_work']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['correct query-coverage projection', 'positive condition must trigger defer']`
- Forbidden attributions: `['Student model instability']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "Fix the compiler's coverage projection so a single first-entity-only query is never labeled as covering both entities: label 'both' only when searches actually cover each entity, and when exactly one search covers the first entity and none covers the second, still emit the required one-shot defer that replaces the pending final.", "applicability": "Applies when the compiler projects query coverage to decide entity-pair deferral; based on one observed mismatch, this is an isolated wiring defect, not a Student capability boundary.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_missing_fact_model_misclassification / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\conformance_missing_fact_model_misclassification\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['teacher_work']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['partial relevance is not the decisive fact', 'revalidate or simplify the semantic boundary']`
- Forbidden attributions: `['Conformance Reviewer error']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "For mechanism_distiller: when a definitive comparison answer's other-entity decisive record is absent from every retrieved passage, the Hook-model evaluator must still emit a positive decision; gating the positive decision on both of two required records being present suppresses the required detection and produced five conformance mismatches.", "applicability": "Applies when mechanism_distiller evaluates definitive comparison answers whose decisive supporting fact is absent from all retrieved passages; the presence of only one of the two records must not suppress the positive decision.", "evidence_refs": ["conformance"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_intrinsic_grounding_predicate\run_01.json`
- Expected primary layers: `['upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "Gating commitment on a single passage explicitly stating the relation made the two-phase withhold/defer mechanism over-conservative: correct retrieval-supported answers were repeatedly deferred, buying only +0.6pp accuracy while increasing instability and cost. Future defer-rule designs must calibrate the commit threshold against retrieval-support fidelity and deferral cost, and evaluations must report deferred-answer correctness separately from committed-answer accuracy instead of one aggregate accuracy delta.", "applicability": "Applies to two-phase withhold/defer answer mechanisms whose upstream contract excludes prior knowledge and gates commitment on explicit single-passage statement.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_intrinsic_grounding_predicate\run_02.json`
- Expected primary layers: `['upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "The withhold/defer commitment rule that requires a single passage to explicitly state the relation before committing was faithfully implemented yet repeatedly deferred correct retrieval-supported answers, yielding only +0.6pp accuracy at higher instability and cost. Future evaluations of deferral mechanisms should calibrate the withhold condition against correct-answer recall (e.g., defer only when retrieval evidence is absent) and must track deferred-correct rate, stability, and cost as primary metrics rather than accuracy alone.", "applicability": "Applies when evaluating candidate two-phase withhold/defer answer mechanisms whose commitment rule is stricter than the available retrieval support warrants, especially with passage-level evidence contracts.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_intrinsic_grounding_predicate\run_03.json`
- Expected primary layers: `['upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `['upstream_contract', 'candidate_comparison']`; successful: `['upstream_contract', 'candidate_comparison']`; failed calls: `0`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "Requiring one passage to explicitly state the relation before committing (excluding prior knowledge and cross-passage entailment, conservative defer) is overstrong: it deferred correct retrieval-supported answers, cutting stable-correct 45→42 and consistency 0.653→0.613, raising unstable 16→20 and ~5.6x tokens, for only 158→160/225 accuracy. Future withhold/defer evaluations must calibrate the defer condition against retrieval-supported correctness (defer only when retrieval evidence is absent or contradicts the candidate) and report defer precision/recall and cost per accuracy point.", "applicability": "When evaluating a withhold/defer or grounding mechanism whose design requires an explicit single-passage statement of the relation; not for implementation defects (conformance passed) or model capability boundaries.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_hook_false_positive_scope\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `['upstream_contract', 'candidate_comparison']`; successful: `['upstream_contract', 'candidate_comparison']`; failed calls: `0`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "A semantic Hook for one-sided two-candidate evidence gaps must be validated on contract-conforming positive probes before cost is accepted: here it fired only on joint and single-entity negatives (one firing flipped a correct 1.0 answer to 0.0), never on an intended positive, while tokens rose ~48% (~430k Hook tokens) and accuracy declined, with any gains coming from Hook-negative no-op runs. Future mechanism evaluations must include positive-class firings and per-mechanism cost-benefit attribution before adoption.", "applicability": "When an evaluation introduces a detection mechanism (e.g., a semantic Hook) whose positive class is defined by an upstream contract, and observed firings fall entirely outside that defined class.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_hook_false_positive_scope\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['student_capability', 'experiment_direction']`
- Tool views: `['upstream_contract', 'candidate_comparison', 'candidate_comparison']`; successful: `['upstream_contract', 'candidate_comparison', 'candidate_comparison']`; failed calls: `0`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"experience_type": "student_capability", "lesson": "The semantic Hook detector fired only on contract-negative cases (a joint A-and-B magazine question and a single-entity question), one firing regressed a correct 1.0 answer to 0.0, and it never fired on any genuine one-sided two-candidate positive, so its activations do not mark the intended evidence gap and are unsafe as an answer-changing signal.", "applicability": "Whenever a semantic Hook or detector is proposed to gate answer changes on contract-defined positive cases, its activations must be treated as unreliable until they have demonstrably fired on genuine positive cases rather than on explicit negatives.", "evidence_refs": ["candidate_review"]}, {"experience_type": "experiment_direction", "lesson": "Evaluation of side-channel detectors must include positive-case validation and a regression/cost gate before integration: here the Hook added roughly 430k tokens (~48% cost), regressed a correct answer, and all observed improvements occurred on Hook-negative no-op runs, so no score gain was attributable to the mechanism.", "applicability": "Applies to research/evaluation designs that introduce semantic detectors into candidate evaluation; gains on detector-negative runs must not be attributed to the detector, and token/accuracy budgets should be enforced.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_hook_false_positive_scope\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `['upstream_contract', 'candidate_comparison', 'candidate_comparison']`; successful: `['upstream_contract', 'candidate_comparison', 'candidate_comparison']`; failed calls: `0`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "Because the semantic Hook's activations were never gated against the contract's explicit negative set, it fired only on contract-negative joint and single-entity questions, regressed a correct 1.0 answer to 0.0, and raised tokens ~48% (about 430k Hook tokens) while the intended positive never fired; future integrations must validate an auxiliary mechanism's outputs against the contract negative rules and measure their score impact before the mechanism may alter candidate answers.", "applicability": "Applies when integrating an auxiliary semantic mechanism into an evaluation whose upstream contract defines explicit negative inputs; require a precision gate on the mechanism's activations against that negative set and a measured false-positive score impact before it can affect answers or costs.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_no_attributed_utility / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_no_attributed_utility\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Required concepts: `['separate activation-attributed utility from no-op variance', 'classifier false positive and cost']`
- Forbidden attributions: `['aggregate improvements prove mechanism benefit']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "Before judging an answer-deferral Hook, evaluations must validate deferral precision against oracle ground truth (definitive answers must never be deferred) and require cost-benefit accounting: in the 75-example run, eight deferral-induced follow-up searches converted no wrong or uncertain answer into a correct one, a definitive Aixam answer was falsely deferred, accuracy and pass@N fell, and total tokens rose by ~271k. Single-run activation counts are insufficient to claim a capability boundary.", "applicability": "Applies to evaluations of mechanisms that gate or defer final answers on evidence-gap signals and trigger follow-up searches: require oracle-labeled deferral decisions, a no-op baseline, tokens-per-converted-answer accounting, and repeated runs before attributing outcomes to a capability boundary.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_low_precision_retrieval / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_low_precision_retrieval\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['low activation precision and low post-deferral efficacy', 'separate no-op variance from mechanism effect']`
- Forbidden attributions: `['Compiler fidelity failure']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "When evaluating a defer/act mechanism like the Hook, compute outcome and cost aggregates only on runs where the mechanism actually activated, or report activated and no-op runs separately: here 3/7 semantic activations violated the negative rule and 4/7 ended wrong, yet most aggregate changes occurred on no-op runs while total tokens nearly doubled, so pooled aggregates conflated the intervention's true effect (and its real token cost) with baseline no-op behavior.", "applicability": "Applies to evaluations of conditional/deferred actions whose activation is sparse, when effect and token-cost aggregates are compared across an entire example set rather than per activation state.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_two_false_positive_activations / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_two_false_positive_activations\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['all observed positive activations violate negative rules', 'no activation-attributed improvement']`
- Forbidden attributions: `['Candidate Reviewer caused rejection']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "When validating a one-shot absence gate over a labeled landscape, enforce a mandatory activation-conformance check against the contract's negative rules before any accuracy scoring: in this evaluation the gate's only two positive activations were explicit contract negatives (a grounded single-entity lookup and a both-entity question), and one of those activations flipped a correct answer to wrong, so end-to-end accuracy alone cannot establish whether an absence gate adds value.", "applicability": "Applies to evaluations of gating/absence-justification candidates whose activation predicate must respect upstream negative rules, especially one-shot gates with sparse activations; treat any activation on a contract-negative case as a gate failure and require activation-driven improvement for acceptance.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_selectivity_and_cost / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_reject_selectivity_and_cost\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Actual types: `['experiment_direction']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['selectivity harm offsets target benefit', 'avoid per-event semantic classification cost']`
- Forbidden attributions: `['one successful case justifies adoption']`
- Output: `{"items": [{"experience_type": "experiment_direction", "lesson": "When a candidate gates extra computation on a trigger predicate (here, a second-entity search), evaluation must include out-of-scope negative cases and cost metrics, not only aggregate accuracy: the over-broad trigger left aggregate accuracy flat while an out-of-scope shared-membership false positive regressed a stable-correct case and total tokens rose about 93%. Validate the trigger's declared scope against the full event distribution, not just the intended cases.", "applicability": "Applies to evaluating any candidate that adds a conditional search/computation stage whose declared scope (e.g., count or possession comparisons with one-sided evidence) is narrower than all events; use attributed per-case outcomes plus token cost to detect regressions masked by aggregate accuracy.", "evidence_refs": ["candidate_review"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_validation_query_coverage_defect / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v2\runs\candidate_validation_query_coverage_defect\run_01.json`
- Expected primary layers: `['implementation']`
- Actual types: `['teacher_work']`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Required concepts: `['change the implementation before resubmission', 'fix coverage and defer action together']`
- Forbidden attributions: `['Candidate Validator error', 'Student capability failure']`
- Output: `{"items": [{"experience_type": "teacher_work", "lesson": "When validation rejection restates the query-coverage and one-shot-deferral obligations, the compiler must actually modify the implementation rather than resubmit unchanged: the coverage label must be backed by a real check that the second entity is matched, so a first-entity-only query is never reported as covering both entities, and the positive condition must emit exactly one defer whose feedback directs a second-entity search.", "applicability": "Applies when candidate validation rejects a compiler submission with repair obligations for query coverage and one-shot deferral on a second-entity search obligation, especially after a prior rejected attempt was resubmitted without changes.", "evidence_refs": ["validation"]}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## Anchor 稳定性

- `evidence_revise_corpus_confound`: type_sets=`[['experiment_direction', 'teacher_work'], ['teacher_work'], ['experiment_direction']]`, type_stable=`False`; semantic stability: TODO
- `hook_feasibility_student_instability`: type_sets=`[['teacher_work'], ['student_capability'], ['teacher_work']]`, type_stable=`False`; semantic stability: TODO
- `conformance_activation_budget_implementation`: type_sets=`[['teacher_work'], ['teacher_work'], ['teacher_work']]`, type_stable=`True`; semantic stability: TODO
- `conformance_semantic_evaluator_boundary`: type_sets=`[['student_capability', 'teacher_work'], ['student_capability'], ['student_capability', 'teacher_work']]`, type_stable=`False`; semantic stability: TODO
- `candidate_reject_intrinsic_grounding_predicate`: type_sets=`[['experiment_direction'], ['experiment_direction'], ['experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `candidate_reject_hook_false_positive_scope`: type_sets=`[['experiment_direction'], ['experiment_direction', 'student_capability'], ['experiment_direction']]`, type_stable=`False`; semantic stability: TODO
