# TASK-007 真实归因质量人工审计模板

每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。

## hook_feasibility_student_instability / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\hook_feasibility_student_instability\run_01.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Frozen Hook model fails the explicit-negative boundary of the three-label one-sided two-entity gap evaluator: with thinking disabled, two valid negatives were repeatedly labeled positive; with thinking enabled, one identical negative flipped across repetitions; positives stayed stable and parse-clean under the confirmed contract. Hypothesis Researcher must not rely on this boundary unchanged; revise the hypothesis or add a deterministic guard/recheck.", "applicability": "Observed scope: frozen Hook model, three-label one-sided two-entity gap evaluator, real-prefix cases, both thinking modes; limit covers only the explicit-negative boundary (positive decisions were stable). Recheck the negative predicate if input scope, mode, or decision contract changes.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\hook_feasibility_student_instability\run_02.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Frozen Hook model repeatedly labels both valid explicit-negative real-prefix cases as positive when thinking is disabled; with thinking enabled one identical negative flips across repetitions, while positives stay stable and parse-clean. The explicit-negative boundary is neither stable nor selective. Hypothesis Researcher must not rely unchanged on this boundary: add a deterministic guard for explicit negatives or recheck under thinking-enabled evaluation before reuse.", "applicability": "Applies only to the frozen Hook three-way decision on one-sided two-entity evidence gaps, real-prefix inputs, thinking-disabled mode (negative boundary also unstable when thinking enabled). A deterministic guard or validated thinking-enabled probe would release the limit before reuse.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\hook_feasibility_student_instability\run_03.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "The frozen Hook model cannot reliably realize the explicit-negative boundary of the three-label evaluator: with thinking disabled, both valid real-prefix negative cases were repeatedly labeled positive, and with thinking enabled one identical negative flipped across repetitions while positive cases stayed parse-clean and stable. Hypothesis Researcher should not rely on this boundary unchanged; add a deterministic explicit-negative guard or run a specified recheck before reuse.", "applicability": "Applies only to the frozen Hook model's three-way decision on explicit single-entity/one-sided negative real-prefix cases under the tested thinking-mode scope. The limit is released by a deterministic explicit-negative guard or by rechecking the model on equivalent negatives before each use.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\distiller_not_distillable_model_boundary\run_01.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen Hook model cannot realize the negative boundary required by the validated activation contract: it mislabeled the valid both-entities-queried negative in 4/4 parse-clean probes and also mislabeled a valid single-entity negative across two contract wordings. Do not rely on this model unchanged for the negative decision; add a deterministic guard or run a specified recheck before deployment.", "applicability": "Applies only to the Hook model on valid both-entity and single-entity negatives within this one-sided-search distillation scope; a recheck run or a re-specified (deterministically guarded) boundary would release the limit.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\distiller_not_distillable_model_boundary\run_02.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Frozen Hook model cannot realize the distilled negative boundary: it mislabeled the valid both-entities-queried negative in 4/4 probes and also mislabeled a valid single-entity negative, with reference, input, and implementation fidelity confirmed. Hypothesis Researcher should not rely on the Hook unchanged for one-sided-search negative rejection; add a deterministic guard or recheck the boundary after a model change.", "applicability": "Applies only to the frozen Hook model's decisions on both-entity and single-entity negative queries within the one-sided-search distillation scope; the limit may be revisited after retraining or replacing the Hook model.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\distiller_not_distillable_model_boundary\run_03.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen Hook model cannot realize the validated activation-contract negative boundary: it mislabeled the required both-entities-queried negative in 4/4 probes and also mislabeled a valid single-entity negative, under parse-clean execution and two contract wordings, with valid inputs and confirmed probe fidelity. Do not rely on the Hook evaluator unchanged; add a deterministic guard for this negative predicate or rerun these probes after a model change.", "applicability": "Applies to the Hook model on the validated one-sided-search negative predicate (both-entity and single-entity negatives) in probe mode under the activation contract; releases when the model is retrained or replaced, or a deterministic guard covering this negative boundary passes both probe cases.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_empty_passage_projection / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\conformance_empty_passage_projection\run_01.json`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['project actual retrieved passages into classifier', 'do not classify on empty evidence']`
- Forbidden attributions: `['Student semantic capability is established as the cause']`
- Output: `{"items": [{"lesson": "The Compiler's Candidate fed an empty placeholder into the semantic classifier even though the Compiler contract required projecting the actual retrieved passages; the classifier therefore decided on an empty passage list while passages existed in the trajectory, producing four mismatches. Recompile so the classifier input equals the real retrieved passages; completion: conformance confirms classifier input matches trajectory passages on every decision.", "applicability": "Applies to Compiler runtime-input projection for the retrieved-passage grounding classifier under conformance review. Do not generalize this run to the Student model or the grounding hypothesis; recheck only after recompilation wires the actual passages into the classifier input.", "evidence_refs": ["conformance"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\conformance_semantic_evaluator_boundary\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "The frozen Hook evaluator, with faithful structural Hook and deterministic action wiring, repeatedly over-triggered: across four valid mismatches it treated explicitly grounded values as positive (explicit-link negatives) and refusals/bare mentions as committed unsupported values (no-committed-value uncertain cases), crossing both boundaries. It cannot realize the defer-only-unsupported three-way decision; do not rely unchanged, add a deterministic guard or recheck the boundary.", "applicability": "Holds for this Hook model on three-way defer evaluation of valid committed-answer and evidence-gap inputs under explicit negative and no-committed-value uncertain contract clauses; recheck if the evaluator, wiring, input format, or decision contract changes.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\conformance_semantic_evaluator_boundary\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "The frozen Hook evaluator, under valid committed-answer and evidence-gap examples with faithful structural wiring, made four mismatches across two distinct boundaries: it treated explicit-link negatives as positive and refusals/bare mentions as committed unsupported values. It cannot reliably gate 'defer only unsupported committed values'. Do not rely unchanged; add a deterministic guard or recheck the three-way boundary.", "applicability": "Observed scope: this Hook model's three-way deferral decisions on valid committed-answer/evidence-gap inputs in conformance evaluation. Before reuse as a deferral gate, recheck on the explicit-negative and no-committed-value boundaries or add a deterministic guard.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\conformance_semantic_evaluator_boundary\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "The frozen Hook evaluator cannot realize \"defer only unsupported committed values\": across four valid mismatches it over-triggered on both required boundaries — explicit-link negatives (grounded values marked positive) and no-committed-value uncertain (refusals/bare mentions treated as committed) — despite faithful structural Hook and action wiring. Do not rely unchanged; add a deterministic guard or recheck before reuse.", "applicability": "Frozen Hook evaluator model; three-way defer boundary over valid committed-answer and evidence-gap inputs under the confirmed conformance spec. Recheck when the boundary or inputs change, or after a deterministic guard is added and revalidated on both negative classes.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\candidate_reject_hook_false_positive_scope\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen semantic Hook model repeatedly classifies explicit contract-negative joint and single-entity questions as Hook-positive (two valid cases; one caused a direct regression), with no observed intended positive behavior. Do not rely unchanged: add a deterministic guard against explicit negatives or run a specified recheck on a positive-opportunity set.", "applicability": "Scope: frozen Hook model, three-way candidate-comparison decisions on valid real evaluation prefixes under explicit contract-negative rules. Recheck by re-testing with a guard or an expanded positive-opportunity set before trusting Hook positives.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook detection of one-sided two-candidate evidence gaps is unsupported by the full comparison: improvements occurred only on Hook-negative no-op runs, accuracy declined, Hook cost rose sharply, and no positive behavior was activation-attributed. Stop unchanged; revisit only with a design demonstrating selective positive-case utility at acceptable cost.", "applicability": "Scope: semantic-Hook mechanisms for evidence-gap detection in this task's three-way candidate-comparison contract. A legitimate revisit requires measured positive-case detection utility and acceptable cost, distinct from the failed selectivity and no-utility evidence.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\candidate_reject_hook_false_positive_scope\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen semantic Hook model positively activated on two valid explicit contract-negative cases (joint and single-entity questions), one causing a direct regression, and never activated on intended positive cases; it cannot maintain a selectivity boundary separating explicit negatives from genuine one-sided evidence gaps. Hypothesis Researcher: do not rely unchanged; add a deterministic negative-rule guard or recheck on a wider explicit-negative set.", "applicability": "Scope: frozen Hook decisions on valid real evaluation prefixes with explicit contract-negative joint/single-entity questions in this candidate trial. The limit is released or rechecked if wider explicit-negative probes show stable non-activation while intended positive cases still trigger.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Using a semantic Hook to detect genuine one-sided two-candidate evidence gaps is not viable as implemented: it activated only on explicit contract-negative questions, produced no intended positive behavior, improved only Hook-negative no-op runs, and cut accuracy while sharply raising Hook cost (no attributed utility). Stop unchanged; revisit only with a redesign that restores selectivity on explicit negatives and separately measures attributed utility.", "applicability": "Mechanism class: semantic Hook gating for one-sided evidence-gap detection on joint/single-entity contract questions in this evaluation setting. A legitimate revisit requires stable non-activation on explicit negatives plus measured positive utility at acceptable cost.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\candidate_reject_hook_false_positive_scope\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen semantic Hook over-triggers: on two valid explicit contract-negative evaluation prefixes (one joint, one single-entity question) it emitted positive activations, one directly causing a regression, and no intended positive behavior occurred. It does not reliably separate explicit negatives from genuine one-sided evidence gaps; do not rely on it unchanged — add a deterministic explicit-negative guard or run the specified recheck.", "applicability": "Frozen Hook model, three-way gap decision on explicit contract-negative joint and single-entity evaluation prefixes in this task. Release when both negative cases and fresh explicit negatives pass without positive activation and genuine gaps show attributed benefit.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook detection of genuine one-sided two-candidate evidence gaps is not supported: positive activations appeared only on explicit negatives, no intended positive behavior was observed, improvements came only from Hook-negative no-op runs, accuracy declined, and Hook cost rose sharply. Stop this mechanism unchanged; revisit only with activation-attributed utility on validated genuine gaps at acceptable cost.", "applicability": "Hook-based evidence-gap detection for one-sided two-candidate questions in this evaluation setting. Revisit only via a new trial showing positive activation on validated genuine gaps, measured attributed benefit, and cost/accuracy within budget.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_validation_unchanged_compiler_work / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4_redundancy_probe\runs\candidate_validation_unchanged_compiler_work\run_01.json`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['change the implementation before resubmission', 'fix coverage and defer action together']`
- Forbidden attributions: `['Candidate Validator error', 'Student capability failure']`
- Output: `{"items": [{"lesson": "Compiler: the resubmission carried the prior validation obligations, yet the Candidate remained unchanged with both deterministic defects (labeling a first-entity-only query as covering both entities; failing to produce exactly one defer with required feedback). Validation rejected the unchanged artifact with repeated obligations and routed to failure analysis. Implement both fixes; completion is a validation pass that no longer reports the unchanged rejected artifact.", "applicability": "Applies to Compiler repair submissions after candidate_validation failures: a resubmission must actually implement the carried query-coverage and one-shot-deferral obligations. An unchanged Candidate is rejected and ends the compile-revise path rather than returning to compilation.", "evidence_refs": ["validation"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## Anchor 稳定性

- `hook_feasibility_student_instability`: type_sets=`[['student_capability'], ['student_capability'], ['student_capability']]`, type_stable=`True`; semantic stability: TODO
- `distiller_not_distillable_model_boundary`: type_sets=`[['student_capability'], ['student_capability'], ['student_capability']]`, type_stable=`True`; semantic stability: TODO
- `conformance_semantic_evaluator_boundary`: type_sets=`[['student_capability'], ['student_capability'], ['student_capability']]`, type_stable=`True`; semantic stability: TODO
- `candidate_reject_hook_false_positive_scope`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`True`; semantic stability: TODO
