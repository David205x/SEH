# TASK-007 真实归因质量人工审计模板

每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。

## hook_feasibility_student_instability / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\hook_feasibility_student_instability\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\hook_feasibility_student_instability\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace']`; successful: `['decision_trace']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Under valid probes with thinking modes enabled and disabled (2 repetitions each), the Student model when used as the Hook evaluator cannot reliably realize the negative boundary of the three-way pre_final decision contract: disabled mode never emits negative (2/2 false positives on trial_002 and trial_003) and enabled mode flips trial_002 between negative and positive within mode.", "applicability": "Frozen Hook model as three-label evaluator of pre_final decisions (two-entity comparative finalized on first-entity-only evidence = positive; single-entity factoid / both-entity query = negative); thinking modes enabled and disabled; reference, inputs, implementation, and repetition count validated.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\hook_feasibility_student_instability\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\hook_feasibility_student_instability\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['upstream_contract', 'decision_trace']`; successful: `['upstream_contract', 'decision_trace']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Under the pre_final three-label Hook decision contract (two-entity comparison finalized on first-entity-only evidence vs single-entity factoid vs both-entity query), the Student model when used as the Hook evaluator cannot reliably label single-entity factoid negatives as negative: with thinking disabled it false-positives trial_002 and trial_003 (2/2 each), and with thinking enabled it flips trial_002 within mode.", "applicability": "Frozen Student/Hook model; pre_final decision phase; three-label decision contract with single-entity factoid negative class; thinking_mode enabled/disabled probes at 2 repetitions.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## hook_feasibility_student_instability / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\hook_feasibility_student_instability\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\hook_feasibility_student_instability\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability']`
- Actual types: `['student_capability']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace']`; successful: `['decision_trace']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-entity negative boundary is unstable', 'revalidate or restrict supported scope']`
- Forbidden attributions: `['Hook Feasibility Reviewer error', 'parser failure']`
- Output: `{"items": [{"lesson": "Under the three-label feasibility evaluator distinguishing two-entity comparisons finalized on first-entity-only evidence (positive) from single-entity factoid or both-entity-query negatives on real trial prefixes, the Student model when used as the Hook evaluator cannot reliably realize the negative boundary: disabled thinking mode false-positives trial_002 and trial_003 in 2/2 repetitions each, and enabled mode is unstable on trial_002.", "applicability": "Real trial prefixes; three-label feasibility decision contract; enabled and disabled thinking modes; two probe repetitions; explicit negatives are single-entity factoids and both-entity queries.", "evidence_refs": ["hook_review"], "experience_type": "student_capability"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\distiller_not_distillable_model_boundary\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\distiller_not_distillable_model_boundary\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the mechanism activation decision on two-entity comparison transcripts, the Student model when used as the Hook evaluator cannot reliably verify query-target naming: it labeled the both-entities-queried explicit negative as activating in 4/4 generations across two contract wordings and the single-entity negative as activating 2/2 in contract 002.", "applicability": "Frozen Student model probed as Hook evaluator on the mechanism activation decision; two-entity comparison questions; explicit-negative inputs where the query names both entities or only the first entity; two distinct contract wordings.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}, {"lesson": "Deferral-to-second-entity-search is trial-confirmed (2/2 positives, 2/2 negatives) but cannot be distilled as a deterministic guard: the pre_final phase has no complete reproducible rule, the only permitted evaluator (hook_model) mislabels the both-entities-queried explicit negative, the boundary is intrinsic so narrowing is impossible, and needs_evidence is inapplicable because frozen-hypothesis trials measure the Teacher intervention, not the compiled Hook backend. Stop unchanged.", "applicability": "Deterministic distillation of the deferral-feedback guard; two-entity comparison questions with a single retrieval; frozen-hypothesis trial evidence measuring the Teacher intervention.", "evidence_refs": ["distillation"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\distiller_not_distillable_model_boundary\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\distiller_not_distillable_model_boundary\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace']`; successful: `['decision_trace']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the three-way Hook decision contract across two distinct contract wordings, the Student model when used as the Hook evaluator cannot reliably classify explicit-negative query targets: it mislabeled both-entities-queried inputs as positive in 4/4 generations, factually asserting the query named only the first entity when it named both, and mislabeled the single-entity negative as positive 2/2.", "applicability": "Frozen classification task through the production model backend as Hook evaluator for the one-shot deferral mechanism's pre_final phase (comparison detection, passage-evidence judgment, query-target verification); explicit-negative inputs: both-entities-queried and single-entity queries.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}, {"lesson": "Deterministic distillation of the one-shot deferral pre_final phase is infeasible: comparison detection, passage-evidence judgment, and query-target verification have no complete reproducible rule, the only permitted Hook evaluator misfires on activation-condition negatives, and the boundary is intrinsic, so narrowing or excusing it as a known limit is impossible. Stop unchanged; revisit only with a contract whose negatives can be classified without the misfiring Hook evaluator.", "applicability": "Mechanism-distillation and evaluation design for the one-shot deferral mechanism's pre_final phase; covers settings where frozen-hypothesis assignments measure the Teacher intervention, not the compiled Hook backend, making needs_evidence inapplicable.", "evidence_refs": ["distillation"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## distiller_not_distillable_model_boundary / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\distiller_not_distillable_model_boundary\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\distiller_not_distillable_model_boundary\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['intervention evidence does not imply deployable evaluator', 'required negative boundary is unrealizable']`
- Forbidden attributions: `['Mechanism Distiller error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under a two-entity, single-retrieval comparison contract requiring the evaluator to verify that the query names only the first entity, the Student model when used as the Hook evaluator cannot reliably classify the query target: it mislabeled both-entities-queried inputs as positive in 4/4 generations across two contract wordings (asserting the query named only the first entity) and mislabeled the single-entity negative as positive in 2/2 in one wording.", "applicability": "Frozen Student model probed as Hook evaluator on the validated two-entity, single-retrieval decision contract; repeated matched probes across two distinct contract wordings; query-target verification and explicit-negative classification.", "evidence_refs": ["distillation"], "experience_type": "student_capability"}, {"lesson": "The deferral intervention is behaviorally validated (2/2 positives, 2/2 negatives, coverage met), but its activation condition's query-target verification has no reproducible deterministic rule; the frozen hook evaluator mislabels the mechanism's own both-entities-queried negative control, a misfire intrinsic to the activation condition that cannot be narrowed, guarded, or excused — distillation stops unchanged; revisit only with an activation condition removing the un-rule-able judgment.", "applicability": "Soft deferral intervention for two-entity single-retrieval comparison questions; distillation into a deterministic guard via the hook_model evaluator; settled mechanism_distiller not_distillable decision.", "evidence_refs": ["distillation"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_empty_passage_projection / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\conformance_empty_passage_projection\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\conformance_empty_passage_projection\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['project actual retrieved passages into classifier', 'do not classify on empty evidence']`
- Forbidden attributions: `['Student semantic capability is established as the cause']`
- Output: `{"items": [{"lesson": "The Compiler wired the pre_final grounding evaluator's 'retrieved passages' input to an empty list instead of the trace's actual passage content, so grounded=false was trivially returned on an empty set, defeating the mechanism's conditional trigger and semantic grounding. Populate passages with the retrieved passage content; completion is met when the pre_final invocation carries the trace's retrieved passages and conformance confirms declared inputs govern the decision.", "applicability": "Compiler implementation of the pre_final grounding evaluator in the candidate-deferral mechanism; applies to conformance's declared-inputs-govern-the-decision fidelity criterion for the grounding classification invocation.", "evidence_refs": ["conformance"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_empty_passage_projection / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\conformance_empty_passage_projection\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\conformance_empty_passage_projection\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `['decision_trace', 'upstream_contract']`; successful: `['decision_trace', 'upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['project actual retrieved passages into classifier', 'do not classify on empty evidence']`
- Forbidden attributions: `['Student semantic capability is established as the cause']`
- Output: `{"items": [{"lesson": "Compiler obligation: pre_final grounding evaluator must receive actual retrieved passages so they govern deferral. Violation: hook_model_input had 'passages': [] though retrieved passages existed in the trace; classifier returned grounded=false on an empty set. Consequence: conditional trigger and grounding defeated despite correct observable actions. Next: populate the passages field with trace's retrieved content. Completion: recheck shows passages populated and grounding governed by them.", "applicability": "Applies to the Candidate implementation of the pre_final grounding evaluator under conformance.revise_implementation: the evaluator invocation must carry the actual retrieved passages from the trace rather than an empty list, and declared inputs must govern the grounding decision.", "evidence_refs": ["conformance"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## conformance_empty_passage_projection / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\conformance_empty_passage_projection\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\conformance_empty_passage_projection\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['implementation']`
- Expected types: `['teacher_work']`
- Actual types: `['teacher_work']`
- Expected Teacher subject: `compiler`; passed: `True`
- Tool views: `['upstream_contract']`; successful: `['upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['project actual retrieved passages into classifier', 'do not classify on empty evidence']`
- Forbidden attributions: `['Student semantic capability is established as the cause']`
- Output: `{"items": [{"lesson": "The Compiler invoked the pre_final grounding evaluator with an empty passage list, so the declared 'retrieved passages' decision input never governed the one-time deferral of ungrounded candidates, failing implementation fidelity. Populate the passages field with the actual retrieved passage content from the trace before invocation. Done when deferral and finalization decisions are observably driven by the actual retrieved passages.", "applicability": "Compiler implementation of the pre_final grounding evaluator for the bridge-question relational deferral mechanism; phase rules were visible to the Compiler, and the mechanism goal requires deferral to be governed by actual retrieved passages.", "evidence_refs": ["conformance"], "experience_type": "teacher_work", "teacher_role_id": "compiler"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_intrinsic_grounding_predicate / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_intrinsic_grounding_predicate\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_intrinsic_grounding_predicate\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['single-passage predicate is intrinsically over-restrictive', 'evaluate broader grounding without repeated over-withhold']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Literal-single-passage grounding over-triggers: the pre_final hook rejected correct retrieval-supported answers (Fox/Human Error 4x to 'cannot be determined'; Splash! mentor 1.0→0.33) since no passage literally states the relation — +0.6pp within noise, 14 vs 15 regressed, stable_correct 45→42, tokens 5.6x. Narrow: withhold only when retrieval lacks support; accept paraphrase/entailment grounding; revisit only with zero stable_correct→failure flips and bounded cost.", "applicability": "Mechanism class: two-phase withhold/defer pre_final grounding hook with literal single-passage grounding and conservative 'cannot be determined' fallback, on search-based two-entity bridge/comparison questions; evaluated on the 225-record bridge set with cost and stability tracking.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_hook_false_positive_scope\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_hook_false_positive_scope\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['upstream_contract', 'candidate_comparison']`; successful: `['upstream_contract', 'candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the pre_final deferral decision contract on real prefixes, the Student model used as the Hook evaluator cannot reliably keep its POSITIVE decision off contract-negative questions: it emits POSITIVE on both a joint 'A and B' question and a single-entity question.", "applicability": "Frozen Student model as Hook evaluator; three-way pre_final deferral decision contract; real material-set prefixes; contract-negative_rule forms (joint A-and-B and single-entity questions).", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Stop unchanged: the pre_final deferral-with-generic-feedback mechanism for one-sided two-candidate 'X or Y' questions produced no beneficial activation (both material-set items were contract-justified negatives), only over-triggered on contract-negatives, lowered accuracy (-0.0178) and pass_at_n (-0.0667) with +48% tokens (~430k hook tokens); gains traced to Student variance. Revisit only with demonstrated beneficial activation on a genuine one-sided case plus cost remediation.", "applicability": "Mechanism class: pre_final single-deferral hook with generic feedback; evaluation setting: material set with contract negative_rule; no valid one-sided two-candidate positive opportunity fired; revisit requires activation-attributed utility and cost control.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_hook_false_positive_scope\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_hook_false_positive_scope\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['upstream_contract', 'candidate_comparison']`; successful: `['upstream_contract', 'candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the pre_final deferral decision contract for explicit one-sided 'X or Y' detection, the Student model when used as the Hook evaluator cannot reliably restrict its defer decision to the two-candidate predicate: on real prefixes it emits POSITIVE for a joint 'A and B' question and for a single-entity question, both explicit contract negatives per the negative_rule.", "applicability": "Validated on real pre_final prefixes under the explicit two-candidate 'X or Y' deferral contract; covers joint A-and-B and single-entity question inputs that must be classified as negative.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Stop unchanged: the pre_final one-shot deferral with generic second-candidate search feedback yielded zero activation-attributed benefit — no applicable 'X or Y' case activated, both activations were contract negatives (one 1→0 regression, one wasted deferral), gains were Student-side variance, and cost was disproportionate (accuracy −0.0178, pass@n −0.0667, tokens +48%, ~430k hook tokens). Revisit only with a genuine one-sided two-candidate case showing a beneficial positive activation.", "applicability": "Mechanism class: one-shot pre_final deferral appending generic feedback to force second-candidate search, under the explicit 'X or Y' decision contract; evaluated on the material set with real search prefixes.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_hook_false_positive_scope\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_hook_false_positive_scope\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['upstream_contract', 'candidate_comparison']`; successful: `['upstream_contract', 'candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Pre-final one-shot deferral with generic feedback produced no beneficial activation on an applicable one-sided 'X or Y' case: positive path fired only on contract-negative questions (one 1→0 regression, one wasted deferral), accuracy -0.0178, pass_at_n -0.0667, tokens +48% (~430k hook tokens), improved replicates hook-negative (Student variance). Stop unchanged; revisit only with either/or discrimination, beneficial positive activation on a genuine one-sided case, and cost remediation.", "applicability": "Hook mechanisms detecting explicit two-candidate 'X or Y' questions at pre_final on one-sided evidence, deferring once with generic search feedback; evaluated on real prefixes under the frozen contract's negative_rule.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_no_attributed_utility / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_no_attributed_utility\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_no_attributed_utility\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['separate activation-attributed utility from no-op variance', 'classifier false positive and cost']`
- Forbidden attributions: `['aggregate improvements prove mechanism benefit']`
- Output: `{"items": [{"lesson": "Stop unchanged: pre_final deferral-with-corrective-feedback (one extra targeted search for the omitted discriminating term) showed zero mechanism-driven gain in the 75-example eval; all 12 improvements were no-op stochastic, while every activation regressed or stayed equal. Accuracy −0.0044, pass_at_n −0.053, tokens +~24% (+271K input), mean_steps +0.14. Revisit only with measured evidence that the follow-up surfaces the missing term and improves verdicts.", "applicability": "Pre_final hook mechanisms that defer an insufficient-evidence final once with corrective feedback when exactly one bundled search covers one conjunct and omits the discriminating term; evaluated on the 75-example candidate eval under the compiled Candidate.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_selectivity_and_cost / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_selectivity_and_cost\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v7\runs\candidate_reject_selectivity_and_cost\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['experiment_direction']`
- Actual types: `['experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['selectivity harm offsets target benefit', 'avoid per-event semantic classification cost']`
- Forbidden attributions: `['one successful case justifies adoption']`
- Output: `{"items": [{"lesson": "Soft Hook note-activation steering a second per-entity retrieval on two-entity questions: stop unchanged. Accuracy stayed flat (0.6711) while answer consistency (0.6533→0.6044) and majority-correct (0.68→0.6667) fell; deltas 7 vs 10 regressed, one improvement activation-attributed; out-of-scope false-positive (5a822d46) caused a mechanism regression; tokens +93%. Revisit only if activation is restricted to the validated count/possession scope with net attributable gains and controlled cost.", "applicability": "Mechanism class: Hook-classified note activation (single-activation budget) steering a second per-entity retrieval on two-entity count/possession questions; evaluated across 225 records with per-entity search evidence, including out-of-scope shared-membership questions.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## Anchor 稳定性

- `hook_feasibility_student_instability`: type_sets=`[['student_capability'], ['student_capability'], ['student_capability']]`, type_stable=`True`; semantic stability: TODO
- `distiller_not_distillable_model_boundary`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`True`; semantic stability: TODO
- `conformance_empty_passage_projection`: type_sets=`[['teacher_work'], ['teacher_work'], ['teacher_work']]`, type_stable=`True`; semantic stability: TODO
- `candidate_reject_hook_false_positive_scope`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['experiment_direction']]`, type_stable=`False`; semantic stability: TODO
