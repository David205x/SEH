# TASK-007 真实归因质量人工审计模板

每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。

## evidence_revise_corpus_confound / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_revise_corpus_confound\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_revise_corpus_confound\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "One-shot deferral with verbatim second-entity-search feedback reliably triggers the intended search (2/2 faithful positives, no leakage), but evidence-citing revision hit only 1/2; trial_004's absence-based answer is confounded because no Cia Berg title-count passage was retrievable. Narrow: pre-verify each positive has confirmable second-entity evidence in the corpus so a later failure is attributable to the mechanism, not corpus insufficiency.", "applicability": "Deferral-and-feedback intervention on post-deferral Student generation for comparative player title-count queries; evaluation of evidence-citing revision requires corpus-sufficiency pre-verification for the second-named entity.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_revise_corpus_confound / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_revise_corpus_confound\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_revise_corpus_confound\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "One-shot deferral plus verbatim feedback reliably triggers a second-entity search (2/2), but evidence-citing revision is unverified: trial_004's absence-based answer is confounded by corpus insufficiency (no retrievable title-count passage for the second-named entity), so failure with retrievable evidence is untested. Continue only if the trial selector guarantees a positive activation with confirmable second-entity evidence; re-test evidence-citing revision and answer flip.", "applicability": "Deferral-feedback mechanism class in comparative player-title tasks; evaluation of second-entity search activation and evidence-citing revision versus corpus-absence conclusions.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_revise_corpus_confound / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_revise_corpus_confound\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_revise_corpus_confound\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design', 'data_environment']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['upstream_contract']`; successful: `['upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['condition success on retrievable evidence', 'corpus sufficiency confound']`
- Forbidden attributions: `['Evidence Reviewer caused the failure', 'Student capability failure is established']`
- Output: `{"items": [{"lesson": "Deferral feedback prompting a second-entity search activates faithfully (4/4; one-shot, verbatim, no leakage) and triggers the named search (2/2), but the success contract's evidence-citing revision (1/2) is unverified: trial_004 revised again from absence because no Cia Berg title-count passage was retrievable. Continue only if the trial selector guarantees retrievable second-entity evidence before the deferral; otherwise stop unchanged.", "applicability": "Post-deferral Student generation with second-entity search feedback, tested in evidence-reviewer trials over two-named-entity comparisons where corpus sufficiency for the second entity is not pre-checked.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_no_differential_effect\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_no_differential_effect\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Student-visible identity-verification instruction before finalizing did not change the Student's post_tool action choice: 3/4 positive trials (incl. the entity-identity confound) ended in unverified final answers (falsifier), and the sole follow-up search matched an untreated baseline that also searched, so no intervention-attributable effect. Stop unchanged; revisit only with a mechanism showing activation-attributed differential search on ambiguous-identity cases.", "applicability": "Soft context-instruction interventions targeting post_tool search-vs-final decisions in entity-identity/attribute-link verification under absent-entity, same-name, and identity-confound ambiguity; covers frozen-model probing where follow-up search also occurs at baseline.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_no_differential_effect\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_no_differential_effect\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Soft verification instruction (search again when the key entity is absent, same-name candidates appear, or the attribute phrase belongs to a differently-named entity) had no differential effect on post_tool action type: 3/4 positive trials still ended in unverified final answers, and the sole search matched an untreated source that also searched. Stop unchanged; revisit only on evidence of an attributable differential effect versus a matched untreated control.", "applicability": "Soft-instruction interventions injected before finalization to change post_tool action type (search vs final answer) in entity/link-verification scenarios; valid mutation with confirmed reference, input, and data boundaries.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_no_differential_effect / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_no_differential_effect\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_no_differential_effect\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['require a differential effect against control', 'reject contradicted causal direction']`
- Forbidden attributions: `['Evidence Reviewer error', 'missing negative coverage caused rejection']`
- Output: `{"items": [{"lesson": "Student-visible verification-instruction insertion is falsified for changing post_tool action type: 3/4 valid positive trials (absent entity, same-name conflicts, partial description, identity confound) ended in unverified final answers, and the sole search success matched an untreated source that also searched, so no intervention-attributable effect. Stop unchanged; revisit only on activation-attributed change in next-generation action type versus matched controls.", "applicability": "Soft Student-visible instruction injection targeting post_tool action selection (search vs final answer) for entity-identity/link verification in valid positive cases with absent entities, same-name conflicts, partial descriptions, or identity confounds.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_harmful_overtrigger\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_harmful_overtrigger\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "Generic attribute-focused context-patch guidance (additional search when no retrieved passage states the asked attribute) is rejected: only 1/2 faithful activations succeeded; trial 002 clean falsifier (omission condition held, Student finalized 'Earl Bakken' with 0 tool calls); trial 003 over-trigger on complete retrieval replaced a correct answer with wrong 'Pirna'. Stop unchanged; revisit only with a trigger shown selective on omission shapes without over-trigger on complete retrievals.", "applicability": "Mechanism class: generic Student-visible context-patch guidance for the post-tool first generation (search vs final answer); problem condition: description-omission and complete first retrievals; evaluation: faithful patch trials with confirmed reference, input, implementation, and data validity.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_harmful_overtrigger\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_harmful_overtrigger\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "Reject the generic attribute-focused follow-up-search guidance unchanged: a clean falsifier on the description-omission shape (condition held, 0 tool calls before finalization) and an over-trigger on a complete first retrieval (correct answer replaced by a wrong one) show the effect is unreliable and harmful. Revisit only if a trigger fires solely when the exact asked attribute is absent, with measured benefit on the omission shape and no regression on complete retrievals.", "applicability": "Mechanism class: Student-visible generic context guidance adding a follow-up-search obligation without naming candidates or answers; evaluated across candidate-list and description-omission first-retrieval shapes under post_tool activation; outcomes judged by teacher labels and tool-call counts.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## evidence_reject_harmful_overtrigger / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_harmful_overtrigger\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\evidence_reject_harmful_overtrigger\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['falsifier and harmful over-trigger', 'do not continue this direction unchanged']`
- Forbidden attributions: `['Evidence Reviewer error']`
- Output: `{"items": [{"lesson": "Generic attribute-focused guidance (search when no retrieved passage states the asked attribute) is unreliable and harmful: 1/2 faithful activations; clean falsifier (trial 002 omission shape: Student finalized 'Earl Bakken' with 0 tool calls); over-trigger (trial 003 complete retrieval: correct answer replaced by wrong 'Pirna'). Stop unchanged; revisit only with a trigger that verifies the omission explicitly and shows no over-trigger on complete retrievals.", "applicability": "Post-tool-activation decision (search call vs final answer) in frozen Student trajectories under a generic attribute-focused context patch; three faithful no-leakage trials covering candidate-list, description-omission, and complete-retrieval shapes.", "evidence_refs": ["review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\hook_feasibility_student_instability\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\hook_feasibility_student_instability\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `True`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Under the pre_final three-label decision contract (question, completed search queries, retrieved passages, final candidate text), the Student model when used as the Hook evaluator cannot reliably label single-entity factoid negatives as negative: disabled mode returned false positives on two valid negatives (2/2 each), and enabled mode flipped one case negative→positive within mode.", "applicability": "Frozen pre_final Hook profile; three-label evaluation distinguishing two-entity comparisons finalized on first-entity-only evidence (positive) from single-entity factoids or both-entity queries (negative); thinking modes enabled and disabled; validated decision contract and case inputs.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\hook_feasibility_student_instability\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\hook_feasibility_student_instability\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace']`; successful: `['decision_trace']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Under valid three-label decision contracts on real prefixes, the Student model when used as the Hook evaluator cannot reliably emit the negative label for single-entity factoid negatives: repeated probes label explicit negatives trial_002 and trial_003 positive (disabled thinking mode 2/2 each), and enabled mode flips trial_002 from negative to positive within mode.", "applicability": "Frozen pre_final Hook evaluator on real prefixes of the three-label judgment (two-entity comparisons on first-entity-only evidence vs single-entity factoids/both-entity queries); probe thinking modes enabled/disabled, 2 repetitions; contract, inputs, fidelity, sufficiency confirmed.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}, {"lesson": "The frozen-Hook three-label evaluator mechanism cannot be compiled as-is: no thinking mode is faithful (disabled mode never labels single-entity factoid negatives, 2/2 false positives on trial_002 and trial_003; enabled mode is 7/8 but flips trial_002 within mode). Continue only if re-validation/tuning on explicit single-entity factoid negatives yields uncertain-boundary evidence before compilation; spec revision is ruled out because the defect is model capability, not contract ambiguity.", "applicability": "Three-label Hook feasibility for decisions on two-entity comparisons finalized on first-entity-only evidence vs single-entity factoids and both-entity queries; real prefixes; probe thinking modes enabled/disabled; routed to research revision, not spec revision.", "evidence_refs": ["hook_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\hook_feasibility_student_instability\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\hook_feasibility_student_instability\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Under the validated three-label hook contract (two-entity comparison vs single-entity factoid vs both-entity query) on pre_final decisions, the Student model when used as the Hook evaluator cannot reliably realize the negative boundary: single-entity factoid negatives (trial_002, trial_003) are false-positived 2/2 in disabled mode, and enabled mode flips the same case negative→positive within mode.", "applicability": "Frozen pre_final Hook as three-label evaluator; inputs are question text, completed search query texts, retrieved passages, final answer text; probe ran thinking modes enabled/disabled with 2 repetitions per case under confirmed reference, input, implementation, and data sufficiency.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\distiller_not_distillable_model_boundary\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\distiller_not_distillable_model_boundary\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the frozen pre_final activation decision where the retrieved query names both entities, the Student model when used as the Hook evaluator cannot reliably verify query targets: it mislabeled the both-entities-queried negative as positive in 4/4 generations across two contract wordings (asserting the query named only the first entity) and mislabeled the single-entity negative positive in 2/2.", "applicability": "Frozen classification task (query-target verification) via the production model backend; pre_final deferral activation contract comparing two named entities; both-entities-queried and single-entity negative inputs; two distinct contract wordings.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}, {"lesson": "One-shot deferral reliably yields the immediate next-generation second-entity search (2/2 positives, 2/2 negatives), but the guard is not distillable: no reproducible deterministic rule exists for the pre_final phase and the frozen Hook evaluator misfires on the intrinsic activation boundary that cannot be narrowed; stop unchanged — revisit only with a reproducible query-target verification rule or a reliable evaluator.", "applicability": "Guard distillation of the pre_final deferral mechanism; activation condition comparing two named entities with a first-entity-only query; hook_model-only evaluation; frozen-hypothesis trial assignments cannot measure the compiled Hook backend.", "evidence_refs": ["distillation"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\distiller_not_distillable_model_boundary\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\distiller_not_distillable_model_boundary\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the deferral activation condition for two-entity comparison questions, the Student model when used as the Hook evaluator cannot reliably verify whether the single retrieval query names both entities: it mislabeled the both-entities-queried negative positive in 4/4 generations across two contract wordings (factually asserting the query named only the first entity) and mislabeled the single-entity negative positive 2/2.", "applicability": "Frozen production model backend as Hook evaluator; deferral activation contract for two-entity comparison; query-target verification with both-entities-queried and single-entity explicit negatives; two distinct contract wordings probed.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}, {"lesson": "The deferral-to-next-generation second-entity-search mechanism is validated by matched control (2/2 positives; 2/2 negatives non-intervened) but cannot be distilled into a deterministic guard: the both-entities-queried boundary is intrinsic to the activation condition, the only permitted hook_model evaluator mislabels it, and needs_evidence cannot measure the compiled Hook backend. Stop unchanged; revisit only with an evaluator or rule passing the both-entities-queried negative control.", "applicability": "Two-entity comparison deferral mechanism; distillation of the activation condition into guards; hook_model-only evaluation under frozen-hypothesis assignment.", "evidence_refs": ["distillation"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\distiller_not_distillable_model_boundary\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\distiller_not_distillable_model_boundary\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the two-entity deferral-activation evaluation contract, the Student model when used as the Hook evaluator cannot reliably verify retrieval query targets: it mislabeled a both-entities-naming query as first-entity-only-positive in 4/4 generations across two contract wordings and mislabeled the single-entity negative positive 2/2 under contract 002.", "applicability": "Frozen Student/Hook evaluator on the production backend; two-entity attribute-comparison deferral activation; both-entities-queried and single-entity-query transcripts; two distinct contract wordings.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}, {"lesson": "The deferral-feedback mechanism (defer → next Student generation retrieves the second entity) is validated 2/2 positives, 2/2 negatives correct, but its activation condition is not distillable: no reproducible pre_final rule exists, the frozen Hook evaluator misfires on the intrinsic both-entities-queried boundary, and frozen-hypothesis trials cannot measure the compiled Hook backend. Stop unchanged; revisit only via an evaluation design that measures the compiled Hook backend boundary.", "applicability": "Deferral-feedback intervention on two-entity attribute-comparison tasks; guard/decision-contract distillation of the pre_final activation phase; frozen-hypothesis trial design.", "evidence_refs": ["distillation"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_empty_passage_projection / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\conformance_empty_passage_projection\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\conformance_empty_passage_projection\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `[]`
- Expected Teacher subject: `compiler`; passed: `False`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['project actual retrieved passages into classifier', 'do not classify on empty evidence']`
- Forbidden attributions: `['Student semantic capability is established as the cause']`
- Output: `{"items": []}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\conformance_semantic_evaluator_boundary\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\conformance_semantic_evaluator_boundary\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "Under the pre_final boundary condition where the most recent retrieval explicitly states the requested attribute together with the committed entity or phrase and no search tool call followed that retrieval, the Student model used as the Hook evaluator cannot reliably emit the negative/pass-through decision: it repeatedly returns positive instead, injecting feedback and consuming the one-shot deferral budget.", "applicability": "Frozen Student model as the pre_final Hook evaluator under the three-way decision contract; observed when returned passages explicitly establish the requested link for the committed entity (negative rule) and for refusal statements committing to no entity (uncertain rule).", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\conformance_semantic_evaluator_boundary\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\conformance_semantic_evaluator_boundary\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'decision_trace', 'decision_trace']`; successful: `['decision_trace', 'decision_trace', 'decision_trace']`; failed calls: `0`
- Duplicate reads: `True`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "Under the pre_final boundary where the most recent retrieval explicitly states the requested attribute or link for the committed entity, the Student model when used as the Hook evaluator cannot reliably perform negative classification, returning positive instead.", "applicability": "Verified retrieval tasks at the pre_final decision point where the most recent retrieved passage explicitly states the requested attribute or link for the committed entity; Student model evaluated as the three-way Hook decision evaluator.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_semantic_evaluator_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\conformance_semantic_evaluator_boundary\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\conformance_semantic_evaluator_boundary\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace']`; successful: `['decision_trace']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic evaluator crosses negative and uncertain boundaries', 'simplify or revalidate evaluator contract']`
- Forbidden attributions: `['Conformance Reviewer error', 'deterministic action wiring is the demonstrated cause']`
- Output: `{"items": [{"lesson": "Under conditions where the retrieved passages explicitly state the requested attribute or link for the entity the final answer commits to, the Student model when used as the Hook evaluator cannot reliably classify the case as negative and instead classifies it as positive.", "applicability": "Three-way Hook decision task on retrieval-QA examples where the most recent retrieval explicitly states the requested attribute or link for the committed entity, in the thinking mode and input format of the tested trials.", "evidence_refs": ["conformance"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_intrinsic_grounding_predicate\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_intrinsic_grounding_predicate\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Single-passage literal grounding (commit only when one passage explicitly states the relation; no cross-passage/prior-knowledge entailment) over-withholds: correct retrieval-supported answers (Fox, Splash!-15, ages) were rejected to deferral, flipping stable_correct→stable_failure (14 regr vs 15 gains; consistency 0.653→0.613; tokens 5.6x+1.24M hook). Disposition: narrow; revisit only if non-literal grounding avoids regressions at bounded cost.", "applicability": "Two-entity bridge/comparison questions answered via search tool where the pre_final hook enforces single-passage literal grounding; the positive loop is verified only when one retrieved passage explicitly states the relation.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_intrinsic_grounding_predicate\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_intrinsic_grounding_predicate\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Single-passage-literal grounding (commit only when one passage explicitly states the relation; no prior knowledge or cross-passage entailment; conservative uncertain fallback) is not viable: it over-withholds correct retrieval-supported answers (Fox rejected 4x until budget exhausted; mentor→15 1.0→0.33; comparison 0.67→0.0), net accuracy +0.6pp within noise, stable_correct 45→42, tokens 5.6x. Stop unchanged; revisit only with a revised grounding predicate and measured selectivity/cost.", "applicability": "Two-entity bridge/comparison questions answered with a search tool under a frozen pre_final Hook requiring one passage to literally state the relation; 225-record evaluation with accuracy, stability, and token-cost attribution.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_intrinsic_grounding_predicate\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_intrinsic_grounding_predicate\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Literal single-passage grounding predicate (one passage must explicitly state the relation) over-withholds: retrieval-supported correct answers were rejected until budget exhaustion (Human Error/Fox -> 'cannot be determined'; Splash! mentor 1.0->0.33; Glenn Hughes 0.67->0.0); accuracy +0.6pp within noise, consistency 0.653->0.613, 15 improved vs 14 regressed, ~5.6x tokens. Stop unchanged; revisit only if grounding accepts retrieval-supported entailment and shows net gains.", "applicability": "Two-entity bridge/comparison questions answered via search tool under a two-phase withhold/defer Hook whose decision contract requires a single retrieved passage to explicitly state the bridging relation.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_hook_false_positive_scope\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_hook_false_positive_scope\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Single-deferral generic feedback for pre_final two-candidate questions reliably triggers a search query referencing the omitted second candidate (2/2 trials) but leaves the final answer unchanged (trial_004 exact_match_delta 0) with no claimed correctness gain. Narrow: define deferral success as verified incorporation of the second candidate into the final answer; revisit only with answer-delta or correctness evidence.", "applicability": "Two-candidate 'X or Y' questions nearing finalization on one-sided retrieval evidence under the one-shot deferral plus generic 'search for the second candidate' feedback mechanism.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_hook_false_positive_scope\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_hook_false_positive_scope\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison', 'candidate_comparison', 'upstream_contract', 'upstream_contract']`; successful: `['candidate_comparison', 'candidate_comparison', 'upstream_contract', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `True`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under real pre_final prefixes of the two-candidate 'X or Y' deferral contract, the Student model when used as the Hook evaluator cannot reliably classify contract-negative questions (a joint 'A and B' question and a single-entity question) as NEGATIVE, instead emitting false-positive POSITIVE deferral triggers.", "applicability": "Student model as Hook evaluator; pre_final prefixes; two-candidate 'X or Y' deferral contract whose negative_rule marks joint A-and-B and single-entity questions as contract-negative; repeated false positives on two explicit negatives.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Pre_final hook-based 'X or Y' deferral is rejected: it never fired on an applicable one-sided two-candidate case, over-triggered only on contract-negatives (1→0 regression, wasted deferral), all gains are Student variance, and cost is disproportionate (~430k hook tokens, +48% tokens, accuracy −0.0178, pass@n −0.0667). Stop unchanged; revisit only with real-prefix either/or discrimination, a beneficial positive activation on a genuine one-sided two-candidate case, and cost remediation.", "applicability": "Mechanism class: pre_final hook detection of one-sided two-candidate 'X or Y' questions with one-shot deferral and generic second-candidate search feedback; real-prefix evaluation under the frozen negative_rule; activation attribution, selectivity, and cost measured.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_hook_false_positive_scope\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_hook_false_positive_scope\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the pre_final Hook decision contract and its negative_rule, the Student model when used as the Hook evaluator cannot reliably classify explicit contract-negative questions as negative: it emitted the positive deferral on a joint 'A and B' question (turning a correct 1.0 replicate into 0.0) and on a single-entity question (wasted deferral).", "applicability": "Frozen Student model as Hook evaluator for the pre_final two-candidate deferral decision; explicit-negative forms per the negative_rule (joint A-and-B, single-entity) on real prefixes.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Single-deferral hook with generic 'search the second candidate' feedback for pre_final one-sided two-candidate questions produced zero beneficial activations on applicable cases; activations misfired on contract-negatives, gains traced to Student-model variance, and tokens rose ~48% (~430k) while accuracy fell -0.0178 and pass@n -0.0667. Stop unchanged; revisit only with either/or discrimination on real prefixes, fresh evidence of beneficial activation on a genuine case, and cost remediation.", "applicability": "Frozen-hook single-deferral mechanisms for one-sided two-candidate 'X or Y' questions at pre_final, under the negative_rule decision contract, evaluated on real prefixes.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_no_attributed_utility / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_no_attributed_utility\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_no_attributed_utility\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['separate activation-attributed utility from no-op variance', 'classifier false positive and cost']`
- Forbidden attributions: `['aggregate improvements prove mechanism benefit']`
- Output: `{"items": [{"lesson": "The pre_final defer-with-feedback mechanism shows no activation-attributed benefit: all 12 eval improvements came from hook-negative no-op or guard-failure no-op paths, every activation case regressed or stayed equal, and Aixam deferred a definitive final, violating the negative rule; cost rose ~24% (+139.9K tokens, ~271K hook input). Stop unchanged; revisit only with proven hook reliability on definitive finals, matched activation-attributed utility, and lower cost.", "applicability": "75-example eval, 8 replicate-activations across 4 cases (Aixam, Jane/First for Women, Cadmium Chloride, Coldplay/Estadio Único); pre_final defer-with-feedback mechanism after a single bundled search retrieval; hook-negative no-op paths as comparison.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_selectivity_and_cost / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_selectivity_and_cost\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_reject_selectivity_and_cost\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison', 'upstream_contract']`; successful: `['candidate_comparison', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['selectivity harm offsets target benefit', 'avoid per-event semantic classification cost']`
- Forbidden attributions: `['one successful case justifies adoption']`
- Output: `{"items": [{"lesson": "Per-event Hook classification inserting a generic second-entity-retrieval note achieves the intended second search (2/2) but over-triggers on an out-of-scope shared-membership question (5a822d46), degrading a stable-correct answer 3/3→1/3; aggregate accuracy is flat while consistency and majority-correct decline, net benefit is ~1 improved vs 1 harmed, and tokens nearly double (~497k Hook tokens). Stop unchanged; revisit only with a cheaper, decision-contract-faithful trigger.", "applicability": "Per-event Hook-model classification of every search event to insert a generic second-entity-retrieval note; two-entity count/possession comparison questions; 225-record rollout evaluated on accuracy, consistency, majority-correct, and token cost.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_validation_unchanged_compiler_work / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_validation_unchanged_compiler_work\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v6\runs\candidate_validation_unchanged_compiler_work\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['change the implementation before resubmission', 'fix coverage and defer action together']`
- Forbidden attributions: `['Candidate Validator error', 'Student capability failure']`
- Output: `{"items": [{"lesson": "The compiler owned faithful implementation of the Mechanism Spec but, with constraints visible, wired query-coverage projection to label a single first-entity-only query as covering both entities and omitted the required defer feedback, failing implementation fidelity; the unchanged Candidate was rejected. Fix the projection and defer feedback (only-first-entity coverage, no second-entity passage, require second-entity search) and verify conformance before re-submission.", "applicability": "Candidate implementation of the defer-once mechanism for absence-based comparative verdicts in two-entity 'A or B' questions where the only search names the first entity and retrieved passages contain no passage about the second entity.", "evidence_refs": ["validation"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
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
- `hook_feasibility_student_instability`: type_sets=`[['student_capability'], ['student_capability', 'experiment_direction'], ['student_capability']]`, type_stable=`False`; semantic stability: TODO
- `distiller_not_distillable_model_boundary`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `conformance_semantic_evaluator_boundary`: type_sets=`[['student_capability'], ['student_capability'], ['student_capability']]`, type_stable=`True`; semantic stability: TODO
- `candidate_reject_intrinsic_grounding_predicate`: type_sets=`[['experiment_direction'], ['experiment_direction'], ['experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `candidate_reject_hook_false_positive_scope`: type_sets=`[['experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`False`; semantic stability: TODO
