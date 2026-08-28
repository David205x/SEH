# TASK-007 真实归因质量人工审计模板

每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。

## candidate_reject_hook_false_positive_scope / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v8_overlap_final\runs\candidate_reject_hook_false_positive_scope\run_01.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v8_overlap_final\runs\candidate_reject_hook_false_positive_scope\run_01_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['upstream_contract']`; successful: `['upstream_contract']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the pre_final three-way decision contract whose negative_rule classifies joint 'A and B' questions and single-entity questions as NEGATIVE, the Student model when used as the Hook evaluator cannot reliably classify contract-negative real prefixes; it emits POSITIVE on both a joint 'A and B' question and a single-entity question, violating the frozen boundary.", "applicability": "Frozen Student model as Hook evaluator on real pre_final QA prefixes; three-way decision contract with negative_rule; joint 'A and B' and single-entity question shapes; no other task conditions validated.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "The pre_final one-shot deferral-with-generic-feedback mechanism provides no attributable benefit: its positive activation never fired on an applicable one-sided two-candidate case, all observed gains trace to Student-side variance, and cost is disproportionate (~430k hook tokens, +48% total tokens, accuracy -0.0178, pass@n -0.0667). Stop unchanged; revisit only with either/or-boundary discrimination, a demonstrated beneficial positive activation on a genuine one-sided case, and cost remediation.", "applicability": "One-shot deferral with generic second-candidate search feedback at pre_final for explicit two-candidate questions, evaluated on QA replicates; scope includes activation attribution and hook-token cost regime.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v8_overlap_final\runs\candidate_reject_hook_false_positive_scope\run_02.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v8_overlap_final\runs\candidate_reject_hook_false_positive_scope\run_02_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the pre_final three-way decision contract with negative_rule on real question prefixes, the Student model when used as the Hook evaluator cannot reliably classify explicit-negative questions (joint 'A and B' and single-entity forms) as NEGATIVE; it emits POSITIVE instead.", "applicability": "Frozen Student-as-Hook evaluator over the pre_final NEGATIVE/POSITIVE/NO-OP decision contract on real question prefixes from the two-candidate evaluation material; explicit-negative cases per negative_rule.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "The pre_final one-shot deferral-with-generic-feedback mechanism for one-sided two-candidate questions produced zero beneficial positive activations on any applicable case and degraded utility (accuracy -0.0178, pass@n -0.0667) and cost (+48% tokens, ~430k hook tokens); stop unchanged, revisiting only with fresh evidence of a beneficial positive activation on a genuine one-sided 'X or Y' prefix and cost remediation.", "applicability": "Deferral mechanisms gated by a frozen-model three-way classifier over pre_final question prefixes in two-candidate reasoning material under a negative_rule contract, evaluated on accuracy, stability, and token cost.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v8_overlap_final\runs\candidate_reject_hook_false_positive_scope\run_03.json`
- Input projection: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v8_overlap_final\runs\candidate_reject_hook_false_positive_scope\run_03_input_projection.json`; passed: `True`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `['candidate_comparison']`; successful: `['candidate_comparison']`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Capability conditional fact shape: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Under the frozen three-way decision contract with negative_rule on real pre-final prefixes, the Student model when used as the Hook evaluator cannot reliably classify explicit-negative questions as NEGATIVE: it emits POSITIVE for both a joint 'A and B' question and a single-entity question, each producing a harmful or wasted deferral.", "applicability": "Frozen Student model as Hook evaluator; decision contract: three-way hook classification with negative_rule; input class: real pre-final prefixes containing explicit-negative questions (joint A-and-B, single-entity); setting: candidate_review evaluation of the two-candidate deferral mechanism.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "The one-shot deferral-with-generic-feedback hook for explicit two-candidate questions shows no attributable benefit: zero beneficial positive activations on applicable cases, two harmful misactivations on explicit negatives, accuracy -0.0178 and pass@n -0.0667, ~430k hook tokens (+48% total), all gains Student-side variance. Stop unchanged; revisit only with real-prefix either/or discrimination, a demonstrated beneficial activation on a genuine one-sided case, and cost remediation.", "applicability": "Mechanism class: pre-final hook deferral with generic feedback for one-sided two-candidate questions; evaluation setting: candidate_review under the negative_rule contract with token-cost accounting.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## Anchor 稳定性

- `candidate_reject_hook_false_positive_scope`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`True`; semantic stability: TODO
