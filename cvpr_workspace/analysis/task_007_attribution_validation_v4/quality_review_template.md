# TASK-007 真实归因质量人工审计模板

每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。

## evidence_revise_corpus_confound / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_revise_corpus_confound\run_01.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "The one-shot pre-final deferral to search for the second named entity did not settle whether one-sided retrieval causes absence-based comparison errors: trial_004 faithfully queried Cia Berg, but returned passages lacked the title-count evidence required by the success condition, so its absence-based conclusion was confounded by missing data (full success 1/2). Disposition: inconclusive — do not treat this run as support for or against the direction.", "applicability": "Hypotheses linking one-sided retrieval to absence-based comparison errors and trials whose success condition depends on corpus-returned second-entity evidence; revisit only when retrieval returns the required evidence, or repeated trials show absence persists despite adequate returns.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_revise_corpus_confound / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_revise_corpus_confound\run_02.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "The claim that one-sided retrieval causes absence-based comparison errors is inconclusive: trial_004 faithfully issued the second-entity query (implementation confirmed), but the corpus returned no title-count evidence, so the success condition could not be judged (full success 1/2) and the absence-based conclusion recurred. Do not stop or confirm the mechanism; revisit only with a success condition and corpus passages that actually contain the second-entity evidence.", "applicability": "One-shot pre-final retrieval-deferral trials on absence-based comparison tasks whose success condition depends on second-entity title-count corpus evidence; does not apply where retrieval data suffices.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_revise_corpus_confound / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_revise_corpus_confound\run_03.json`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "The claim that one-sided retrieval causes absence-based comparison errors is untested, not refuted: trial_004 faithfully ran the second-entity search for Cia Berg, but the corpus returned no title-count evidence, so the success condition could not be judged and the absence-based conclusion recurred. Disposition: inconclusive, stop unchanged; revisit only when corpus passages contain the second entity's title-count evidence so the causal effect can be evaluated.", "applicability": "One-shot pre-final deferral prompts that add a named-entity search in absence-based comparison tasks; applies only where retrieval can return the required second-entity evidence. Releases when data sufficiency for the target entity is confirmed and the same trial is re-run.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_reject_no_differential_effect\run_01.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Inserting a generic verification-context block before finalization does not cause a follow-up search: 3 of 4 faithful positive activations finalized without searching, and the lone search success also occurred in the untreated source control, so the treated branch produced no differential action-type effect. Stop unchanged; revisit only with an activation-attributed mechanism and a differential effect against matched controls.", "applicability": "Soft insertion of generic verification context into faithful positive activations before finalization on this trajectory. A legitimate revisit needs a redesigned mechanism whose follow-up search is activation-attributed and differentially absent in untreated controls.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_reject_no_differential_effect\run_02.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Inserted verification context caused no differential follow-up-search behavior: 3 of 4 faithful positive activations finalized without a follow-up search, the sole search success also occurred in its untreated source control, and the declared falsifier dominated faithful positives. Stop this generic inserted-context direction unchanged; revisit only if a redesigned mechanism shows control-differential, activation-attributed search before finalization.", "applicability": "Generic verification-block insertion intended to trigger follow-up search on positive activations in this environment and decision scope; legitimate revisit requires a mechanism whose predicted action differs from matched source control with activation attribution, not more context insertion.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_reject_no_differential_effect\run_03.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Inserting a generic verification block into faithful positive activations does not cause a follow-up search before finalization: three of four activations finalized without search, and the sole search success also occurred in the untreated source control, so the treated branch had no differential action-type effect. Stop this generic-insertion mechanism unchanged; revisit only with a mechanism whose effect is attributable to the intervention and differential against matched controls.", "applicability": "Generic inserted-verification-context mechanisms on frozen positive trajectories evaluated against matched source controls; a legitimate revisit requires a new hypothesis that yields a differential action-type effect and a follow-up search absent from untreated controls.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_reject_harmful_overtrigger\run_01.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "The generic evidence-gap patch is not selective as a follow-up-search mechanism: of two faithful positive activations only one re-searched while the clean falsifier immediately finalized wrong, and a complete-evidence trial over-triggered, flipping a correct answer to wrong. Stop this generic direction unchanged; revisit only with a patch that activates on every true evidence gap and never over-triggers on complete evidence.", "applicability": "Generic evidence-gap patches intended to induce follow-up search; excludes evidence-specific mechanisms. Revisit only if a revised patch shows activation on all positive gap cases and zero over-trigger on complete-evidence controls in matched trials.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_reject_harmful_overtrigger\run_02.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "Generic evidence-gap patches lack selectivity: the faithfully applied patch missed an intended positive (clean falsifier immediately finalized wrong) and over-triggered on complete evidence, changing a correct answer to wrong. Disposition: stop unchanged. A legitimate revisit requires a gap signal that verifies missing facts before triggering, with matched no-trigger controls.", "applicability": "Applies to generic evidence-gap patch mechanisms for inducing follow-up search in this falsifier/complete-evidence evaluation setting; not transferable to gap-detection designs that verify missing facts before triggering.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\evidence_reject_harmful_overtrigger\run_03.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "Stop unchanged: the generic evidence-gap patch is not selective. Of two faithful positive activations, only one induced the needed follow-up search (the clean falsifier immediately finalized wrong), and the same patch over-triggered on complete evidence, changing a correct answer to wrong. Revisit only if a revised patch triggers search solely on confirmed evidence gaps, with activation-attributed benefit and no complete-evidence harm.", "applicability": "Applies to generic evidence-gap patches intended to induce follow-up search; does not establish a frozen-model capability boundary. Recheck only with a selective trigger verified per activation against complete-evidence cases before any reuse.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\hook_feasibility_student_instability\run_01.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Frozen Hook model, on valid real-prefix inputs with faithful parse-clean probes, repeatedly labels explicit single-entity negatives as positive: with thinking disabled both negative cases are repeatedly positive, and with thinking enabled one identical negative flips across repetitions, while positives stay stable. The explicit-negative boundary is unstable, so Hypothesis Researcher must not rely on it unchanged: add a deterministic negative guard or run a recheck probe before reuse.", "applicability": "Applies only to the frozen Hook model's three-way negative decision on explicit single-entity negatives under valid real-prefix inputs in this task; recheck the negative boundary before reuse in other modes/tasks or after adding a deterministic guard.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}, {"lesson": "The three-label evaluator direction for one-sided two-entity evidence gaps, realized by thinking-mode probing of the frozen Hook model, fails negative selectivity: explicit negatives are repeatedly labeled positive while positive cases stay stable and parse-clean, isolating failure to the negative boundary. Stop unchanged this probing-only realization; narrow the direction so explicit negatives are decided by a deterministic guard, not further model probes.", "applicability": "Applies to frozen-Hook realization of a three-label evaluator for one-sided two-entity evidence gaps; revisitable only if the negative class is removed from model labeling or a deterministic guard is added.", "evidence_refs": ["hook_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\hook_feasibility_student_instability\run_02.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Frozen Hook model (three-label evaluator) has an unreliable explicit-negative boundary: with thinking disabled, both valid real-prefix negative cases were repeatedly labeled positive; with thinking enabled, one identical single-entity negative flipped across repetitions, while positives stayed stable and parse-clean. Do not rely on this evaluator unchanged; Hypothesis Researcher should add a deterministic guard for explicit negatives or run a specified recheck.", "applicability": "Frozen Hook three-label evaluator on valid real-prefix cases for one-sided two-entity evidence gaps, both thinking modes, with reference/input/fidelity confirmed. Recheck only after repeated explicit-negative rejection is demonstrated.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}, {"lesson": "Realizing a three-label evaluator for one-sided two-entity evidence gaps by toggling the frozen model's thinking mode lacks negative-side selectivity: thinking off removes the repetition flip but both explicit negatives stay positive; thinking on leaves an identical negative flipping across repetitions. Neither mode gives stable explicit-negative rejection. Stop unchanged; revisit only with a design that repeatedly rejects explicit negatives while positives remain parse-clean.", "applicability": "Mechanism class: three-label evaluators for one-sided two-entity evidence gaps realized by frozen-model thinking-mode behavior on real-prefix probes; not applicable to deterministic-guard designs.", "evidence_refs": ["hook_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\hook_feasibility_student_instability\run_03.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Frozen Hook three-label evaluator cannot stably realize the explicit-negative boundary: with thinking disabled, two valid single-entity negatives were repeatedly labeled positive; with thinking enabled, one identical negative flipped across repetitions while positives stayed stable and parse-clean. Hypothesis Researcher must not rely unchanged on this boundary; revise via a deterministic guard or a specified recheck.", "applicability": "Scope: frozen Hook model, three-label decision contract, valid real-prefix one-entity negative cases, both thinking modes, repeated identical probes. Recheck or release the limit if the evaluator is retrained, a deterministic explicit-negative guard is added, or the decision contract is changed.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\distiller_not_distillable_model_boundary\run_01.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen Hook model cannot realize the distilled one-sided-search negative boundary: on valid both-entity and single-entity negatives from the validated activation contract, it mislabeled the both-entity negative in 4/4 probes under two contract wordings with parse-clean execution, and also mislabeled a single-entity negative. Hypothesis Researcher: do not rely on this model unchanged; add a deterministic guard or run a specified boundary recheck before deploying the evaluator.", "applicability": "Scope: this Hook model, one-sided-search task, both-entity and single-entity explicit negatives, distilled three-way decision mode. Limit lifts with a different model passing capability probes or a deterministic guard covering explicit negatives.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\distiller_not_distillable_model_boundary\run_02.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Only permitted frozen Hook model mislabeled the valid both-entities-queried negative in 4/4 probes and also a valid single-entity negative, with reference, input, and probe fidelity confirmed; it cannot realize the required activation-contract negative boundary. Hypothesis Researcher: do not rely unchanged; add a deterministic negative guard or recheck on the same probes.", "applicability": "Frozen Hook model, three-way contract, valid both-entity and single-entity explicit-negative probes; limit holds until the model is changed or a deterministic negative guard is added and re-verified on those probes.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}, {"lesson": "Distilling the validated one-sided-search intervention into a deployable Hook evaluator is not realizable: the intervention passed two positive and two negative controls, yet the only permitted Hook model cannot realize the required negative boundary. Stop unchanged; revisit only with a deterministic negative guard or a model verified to preserve the boundary.", "applicability": "Applies to distillation of activation-boundary interventions onto the frozen Hook model under the validated contract; releases only when a realization is verified to preserve the negative boundary on the same controls and probes.", "evidence_refs": ["distillation"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\distiller_not_distillable_model_boundary\run_03.json`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The permitted Hook model cannot realize the validated negative boundary: it mislabeled the both-entities-queried negative in 4/4 probes and also mislabeled a single-entity negative; two contract wordings and parse-clean probe execution rule out parser or wiring defects. Hypothesis Researcher should not rely on this Hook unchanged: add a deterministic guard or run a specified recheck of the negative boundary.", "applicability": "Applies to this Hook model on the one-sided-search evaluator task with valid both-entity and single-entity negatives under the current activation-contract wording. The limit is released if a different frozen model or a deterministic negative filter can realize the boundary on a recheck.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}, {"lesson": "Intervention validity does not transfer to deployability: the upstream one-sided-search intervention passed two positive and two negative controls, yet the permitted Hook evaluator could not realize the required negative boundary, so distilling it into a deployable Hook evaluator is not supported. Stop this distillation path unchanged; require deployment-boundary evidence or a model change before revisit.", "applicability": "Applies to distillation of validated activation-contract boundaries into a deployable Hook evaluator for one-sided-search negatives. Revisit only with a different frozen model, a deterministic guard, or evidence that the boundary is realizable in deployment.", "evidence_refs": ["distillation"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_empty_passage_projection / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\conformance_empty_passage_projection\run_01.json`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['experiment_direction', 'teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['project actual retrieved passages into classifier', 'do not classify on empty evidence']`
- Forbidden attributions: `['Student semantic capability is established as the cause']`
- Output: `{"items": [{"lesson": "Direction untested: the relation-grounding trial is vacuous because the Candidate's semantic classifier received an empty passage list while actual retrieved passages existed in the trajectory, so the semantic decision ignored the contract's declared input. Do not read this run as evidence against passage-grounded relation classification; treat the direction as inconclusive and revisit only with a conformant projection of the actual retrieved passages.", "applicability": "Applies to semantic classification of retrieved passages for explicit relation grounding in this Evolution trial; releases when a conformant Candidate feeds the actual trajectory passages to the classifier and the decision is re-evaluated.", "evidence_refs": ["conformance"], "experience_type": "experiment_direction"}, {"lesson": "Compiler: the Mechanism Spec contract required projecting the actual retrieved passages into the Candidate's semantic classifier, but the Candidate passed an empty placeholder, producing four conformance mismatches and the revise_implementation decision. Rebuild the Candidate to pass the actual trajectory passages; completion is conformance confirming classifier input equals the retrieved passages.", "applicability": "Applies to compiler implementation of the retrieved-passage projection contract for the relation-grounding classifier; complete when conformance review confirms the classifier receives the actual retrieved passages.", "evidence_refs": ["conformance"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\conformance_semantic_evaluator_boundary\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "Frozen Hook model over-triggers deferral: across four valid mismatches it treated explicitly grounded values as positive and refusals/bare mentions as committed unsupported values, despite faithful structural Hook and deterministic action wiring. Boundary: cannot reliably implement 'defer only unsupported committed values' on explicit-negative or no-committed-value uncertain inputs. Hypothesis Researcher: do not rely unchanged; add a deterministic guard or run a recheck.", "applicability": "Scope: Hook-model three-way deferral evaluator on committed-answer and evidence-gap inputs under explicit-negative and uncertain contract clauses, faithful wiring. Recheck/release: different evaluator model or added deterministic guard shown selective on the same two boundaries.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}, {"lesson": "Hook-evaluator direction 'defer only unsupported committed values' is falsified as designed: with structural Hook and deterministic action wiring faithful, the evaluator violated both explicit-link negative and no-committed-value uncertain boundaries across four mismatches. Disposition: stop unchanged. Revisit only with evidence that a revised evaluator design attains selectivity on both boundary classes.", "applicability": "Mechanism class: Hook-model-based three-way deferral/conformance evaluator. Problem condition: explicit negatives and no-committed-value uncertainty under faithful implementation. Revisit requires revised evaluator design with matched-control selectivity on both boundaries.", "evidence_refs": ["conformance"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\conformance_semantic_evaluator_boundary\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "Frozen Hook-model evaluator: with faithful wiring, valid inputs, and confirmed labels, it classified valid explicit-negative and no-committed-value cases as positive committed-unsupported values across four mismatches in two boundaries. It cannot reliably separate supported, committed-unsupported, and no-committed-value decisions. Do not rely unchanged; add a deterministic guard or run a recheck on these probes.", "applicability": "Scope: Hook-model three-way defer decisions on committed-answer and evidence-gap inputs in conformance evaluation. Limit releases only if a recheck shows correct classification of explicit-negative and uncertain cases.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}, {"lesson": "Direction 'use a Hook-model evaluator to defer only unsupported committed values' is not selective: despite faithful implementation and valid inputs, it over-triggered on explicit negatives and on refusals/bare mentions (four mismatches, two boundaries). Stop unchanged; revisit only with a redefined three-way contract plus matched probes showing no over-trigger.", "applicability": "Applies to this evaluator-based deferral mechanism class for conformance committed-answer/evidence-gap decisions, not other mechanisms. Legitimate revisit requires a redefined decision boundary and explicit-negative/uncertain matched-probe evidence.", "evidence_refs": ["conformance"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\conformance_semantic_evaluator_boundary\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "The frozen Hook evaluator, on valid committed-answer/evidence-gap inputs with faithful structural and action wiring, repeatedly treated explicit-link negatives and refusals/bare mentions as committed positives (4 mismatches spanning both boundaries). It cannot reliably defer only unsupported committed values. Hypothesis Researcher: do not rely unchanged; add a deterministic guard for explicit negatives and no-committed-value cases, or recheck the three-way boundary.", "applicability": "Applies only to the frozen Hook model's three-way deferral evaluation on this task's committed-answer/evidence-gap decision scope (explicit-link negative and no-committed-value boundaries). Rechecking the boundary or adding a deterministic guard for these classes would release the limit.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_reject_intrinsic_grounding_predicate\run_01.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Requiring a single passage to explicitly state the relation before committing an answer (two-phase withhold/defer) matched the incumbent at +0.6pp accuracy while decreasing stable-correct answers, adding 14 regressions vs 15 improvements, raising tokens ~5.6x, and repeatedly deferring correct retrieval-supported answers. Stop unchanged; revisit only if a redesigned predicate shows differential benefit on targeted cases without net regression or cost.", "applicability": "Retrieval QA with single-passage explicit-statement grounding predicates and withhold/defer mechanism designs, evaluated on the same 225 records. Recheck would require evidence of net accuracy gain and acceptable cost on explicit-negative or ambiguous cases.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_reject_intrinsic_grounding_predicate\run_02.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Single-passage explicit-relation grounding predicate (withhold/defer mechanism) is not viable: conformance-passing run on 225 records gained only +0.6pp, stable-correct fell, instability rose, tokens ~5.6x, correct retrieval-supported answers repeatedly deferred (14 regressions vs 15 improvements). Stop unchanged; revisit only with a revised predicate avoiding correct-answer deferral at bounded cost.", "applicability": "Applies to two-phase withhold/defer answer mechanisms gated on single-passage explicit-relation grounding in retrieval-supported QA; not evidence about the frozen Student model's own boundary. Release condition: a revised predicate with near-zero correct-answer deferral and bounded token cost.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_reject_intrinsic_grounding_predicate\run_03.json`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Single-passage grounding predicate (withhold/defer unless one passage explicitly states the relation) changes accuracy only +0.6pp on 225 matched records: 14 regressions vs 15 improvements, repeated deferral of correct retrieval-supported answers, and ~5.6x token cost despite conformance passing. Disposition: stop unchanged; revisit only if deferral-precision/recall evidence shows protected errors outweigh lost correct answers at acceptable cost.", "applicability": "Applies to two-phase withhold/defer grounding mechanisms over retrieval-supported QA in this 225-record evaluation scope; it does not establish a Student or Hook model capability boundary. A legitimate revisit requires selectivity and cost evidence beyond aggregate accuracy.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_reject_hook_false_positive_scope\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen Hook model positively activates on explicit contract-negative joint and single-entity evaluation questions (two valid cases; one caused a direct regression) while producing no intended positive behavior. This repeated false-positive activation establishes a narrow selectivity boundary: the Hook cannot be relied on unchanged for one-sided evidence-gap detection. Hypothesis Researcher: add a deterministic guard or run a specified recheck probe before any reuse.", "applicability": "Scope: frozen Hook model, semantic mode, valid evaluation prefixes of contract-negative joint and single-entity questions. Release: zero activation on these explicit negatives with preserved positive detection would revisit the limit.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook detection of one-sided two-candidate evidence gaps is not selective or useful: activations occurred only on explicit contract negatives (one regressed), no intended positive behavior appeared, and the matched comparison showed gains only on Hook-negative no-op runs with lower accuracy and sharply higher Hook cost. Disposition: stop unchanged. Revisit only with activation-attributed utility on genuine gaps and no over-trigger on explicit negatives.", "applicability": "Applies to semantic-Hook gating mechanisms for evidence-gap detection in two-candidate evaluation with explicit negative rules; utility must be shown by matched treated/control comparison excluding no-op paths and including cost.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_reject_hook_false_positive_scope\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen Hook model cannot selectively detect genuine one-sided two-candidate gaps: on two valid real evaluation prefixes that are explicit contract-negative (joint and single-entity), it activated positively and one activation caused a direct regression, with no intended positive behavior. Hypothesis Researcher: do not rely on it unchanged; add a deterministic guard for explicit contract-negative cases or rerun a matched explicit-negative recheck.", "applicability": "Applies to the frozen Hook model's three-way semantic decision on this task's contract-negative joint and single-entity evaluation prefixes. Recheck only if the Hook model is retrained, the decision contract changes, or a matched explicit-negative probe set is added.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook detection of one-sided two-candidate evidence gaps shows no attributed utility: positive activations occurred only on explicit contract-negative cases (one caused a regression); improvements appeared only on Hook-negative no-op runs while accuracy declined and Hook cost rose sharply. Disposition: stop unchanged. A legitimate revisit requires activation-attributed positive benefit on valid gap cases plus accuracy and cost parity.", "applicability": "Applies to semantic-Hook-based gap detection for two-candidate evaluation on this task's contract and prefixes. Revisit only under a revised hypothesis that attributes improvements to Hook-positive cases, with matched controls and cost accounting.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_reject_hook_false_positive_scope\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Frozen semantic Hook model over-triggers on explicit negatives: two valid contract-negative evaluation prefixes (joint and single-entity questions) each produced positive Hook activations, one causing a direct regression, with no intended positive behavior observed. The Hook's semantic-positive signal cannot be relied on unchanged to detect one-sided two-candidate gaps; hypothesis_researcher must add a deterministic guard against explicit negatives or run a specified recheck before reuse.", "applicability": "Applies only to this Hook model's semantic-positive decision on valid two-candidate evaluation prefixes in this task/input/mode scope; release the limit only if a guard or recheck shows zero positive activation on explicit contract-negative cases with positive detection preserved.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook defer for one-sided two-candidate gaps is stopped unchanged: positive activations occurred only on contract-negative joint and single-entity questions (one caused a direct regression), no intended positive behavior appeared, and gains were confined to Hook-negative no-op runs while accuracy declined and Hook cost rose — no activation-attributed utility. Revisit only with a redesigned boundary firing on intended gaps with attributed benefit at bounded cost.", "applicability": "Applies to semantic-Hook defer mechanisms for detecting one-sided two-candidate evidence gaps in this task's evaluation setting; excludes deterministic guard designs and non-Hook detection approaches.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_no_attributed_utility / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_reject_no_attributed_utility\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['separate activation-attributed utility from no-op variance', 'classifier false positive and cost']`
- Forbidden attributions: `['aggregate improvements prove mechanism benefit']`
- Output: `{"items": [{"lesson": "Deferral of evidence-gap final answers to induce targeted follow-up search fails utility: eight conformant one-shot Hook activations produced no new correct answer, every activated case regressed or stayed equal, accuracy fell, and Hook cost added ~271k input tokens; all gains came from no-op paths. Stop unchanged; revisit only if targeted follow-up on deferred items demonstrably converts them to correct answers within acceptable cost.", "applicability": "One-shot Hook deferral of evidence-gap answers in this 75-example evaluation task. A revisit requires matched trials showing follow-up search on deferred items yields new correct answers with token cost at or below the observed added penalty.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_selectivity_and_cost / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_reject_selectivity_and_cost\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['selectivity harm offsets target benefit', 'avoid per-event semantic classification cost']`
- Forbidden attributions: `['one successful case justifies adoption']`
- Output: `{"items": [{"lesson": "Second-entity search over-fires on nearly every search event: one count/possession case improved, but an out-of-scope shared-membership case caused a stable-correct regression; aggregate accuracy was flat, consistency and majority-correct declined, regressions exceeded improvements, and tokens rose ~93%. Narrow the trigger to explicit one-sided evidence; revisit only with activation-attributed proof that out-of-scope cases do not trigger and regressions < improvements at bounded cost.", "applicability": "Soft second-entity search trigger for count or possession comparisons with one-sided evidence in Student rollouts. Direction-level only; not a frozen-model capability claim. Applies to trigger-condition selectivity and token-cost design.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_validation_unchanged_compiler_work / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v4\runs\candidate_validation_unchanged_compiler_work\run_01.json`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['experiment_direction', 'teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['change the implementation before resubmission', 'fix coverage and defer action together']`
- Forbidden attributions: `['Candidate Validator error', 'Student capability failure']`
- Output: `{"items": [{"lesson": "Query-coverage plus one-shot deferral for the second-entity search obligation is untested, not refuted: the resubmitted Candidate was unchanged and kept both deterministic defects, so the repeated rejection is an implementation-fidelity confound. Treat the direction as inconclusive; revisit only with a faithfully changed Candidate that satisfies the both-entity coverage and exactly-one-defer obligations.", "applicability": "Applies to Candidate-validation rejections of unchanged resubmissions where implementation fidelity is the failed gate; does not bound the Student/Hook model nor the coverage/deferral mechanism's validity.", "evidence_refs": ["validation"], "experience_type": "experiment_direction"}, {"lesson": "The Compiler resubmitted the Candidate unchanged although the resubmission carried the specific prior validation obligations (both-entity coverage and exactly one defer with feedback); both deterministic defects remained and validation rejected it again. The Compiler must implement and verify those fixes before resubmitting; completion condition is a changed Candidate that passes both obligations.", "applicability": "Applies to Compiler resubmissions after validation failure when role_input_sufficiency confirms the obligations were carried at decision time; does not extend to mechanism-spec ambiguity or frozen-model boundaries.", "evidence_refs": ["validation"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
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
- `hook_feasibility_student_instability`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability']]`, type_stable=`False`; semantic stability: TODO
- `distiller_not_distillable_model_boundary`: type_sets=`[['student_capability'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`False`; semantic stability: TODO
- `conformance_semantic_evaluator_boundary`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability']]`, type_stable=`False`; semantic stability: TODO
- `candidate_reject_intrinsic_grounding_predicate`: type_sets=`[['experiment_direction'], ['experiment_direction'], ['experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `candidate_reject_hook_false_positive_scope`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`True`; semantic stability: TODO
