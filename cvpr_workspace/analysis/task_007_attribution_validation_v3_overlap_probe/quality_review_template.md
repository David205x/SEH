# TASK-007 真实归因质量人工审计模板

每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。

## candidate_reject_hook_false_positive_scope / run 1

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v3_overlap_probe\runs\candidate_reject_hook_false_positive_scope\run_01.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "Frozen semantic Hook positively activated and deferred on two valid explicit contract-negative prefixes (a joint and a single-entity question), misclassifying explicit negatives as evidence gaps, while intended positive cases never activated. Narrow boundary: the Hook cannot selectively gate one-sided two-candidate gaps without over-triggering on explicit negatives. Hypothesis Researcher: do not rely unchanged; add a deterministic explicit-negative guard or run a specified recheck.", "applicability": "Scope: frozen semantic Hook in two-candidate evaluation on valid explicit contract-negative joint and single-entity questions, faithful wiring. Recheck: a Hook variant that passes explicit-negative prefixes without activation (verified on matched positives) or a deterministic negative pre-filter.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook detection of genuine one-sided two-candidate evidence gaps lacks selectivity and utility: activations occurred only on explicit negatives (one directly regressed), no intended positive behavior appeared, and gains came only from Hook-negative no-op runs while accuracy declined and Hook cost rose sharply. Disposition: stop unchanged; revisit only with activation-attributed benefit on positives and no negative over-trigger.", "applicability": "Mechanism class: semantic Hook gating of one-sided evidence gaps in two-candidate review; contract-negative joint/single-entity cases plus aggregate accuracy/cost. Revisit: activation-attributed benefit over matched controls with no negative over-trigger.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 2

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v3_overlap_probe\runs\candidate_reject_hook_false_positive_scope\run_02.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen semantic Hook model repeatedly misclassifies explicit contract negatives as deferral-worthy: two valid explicit-negative questions (one joint, one single-entity) both produced Hook-positive activations, one directly regressing the trajectory, with no positive-case activation observed. The Hook cannot separate explicit negatives from genuine one-sided gaps. Hypothesis Researcher: do not rely unchanged; add a deterministic guard on explicit contract-negative inputs before reuse.", "applicability": "Observed for the Hook model's three-way deferral decisions in valid evaluation prefixes with explicit contract-negative joint and single-entity questions; limit releases only with a wider matched probe including true one-sided-gap positives or a deterministic guard.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Semantic-Hook deferral for one-sided two-candidate evidence gaps carries no attributed utility: accuracy declined, Hook cost rose sharply, and every improvement came from Hook-negative no-op runs while activations hit only explicit negatives. Stop unchanged; revisit only with activation-attributed positive-case benefit, bounded Hook cost, and demonstrated selectivity on explicit negatives.", "applicability": "Applies to semantic-Hook deferral mechanisms in candidate evaluation over contract-negative joint and single-entity questions; does not extend to Hook variants that never fire or settings without per-activation cost and utility attribution.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## candidate_reject_hook_false_positive_scope / run 3

- Artifact: `D:\_Project\Agent\search_harness\cvpr_workspace\analysis\task_007_attribution_validation_v3_overlap_probe\runs\candidate_reject_hook_false_positive_scope\run_03.json`
- Expected primary layers: `['student_capability', 'upstream_design']`
- Expected types: `['student_capability', 'experiment_direction']`
- Actual types: `['student_capability', 'experiment_direction']`
- Expected Teacher subject: `None`; passed: `True`
- Tool views: `[]`; successful: `[]`; failed calls: `0`
- Duplicate reads: `False`; fuse not reached: `True`
- Required concepts: `['semantic classifier fires on explicit negatives', 'no activation-attributed benefit']`
- Forbidden attributions: `['Candidate Reviewer error', 'Compiler implementation defect']`
- Output: `{"items": [{"lesson": "The frozen Hook model produces positive activations on two valid explicit contract-negative evaluation prefixes (joint and single-entity questions; one caused a direct regression) and shows no intended positive detection, with reference validity, input validity, and Candidate fidelity confirmed. Narrow false-positive boundary: do not rely unchanged; add a deterministic guard excluding explicit negatives or run a recheck on valid positives.", "applicability": "Applies to this task's explicit contract-negative inputs in the three-way semantic Hook decision mode under the confirmed evaluation set; revisit if reference rules, input distribution, or decision mode change.", "evidence_refs": ["candidate_review"], "experience_type": "student_capability"}, {"lesson": "Faithfully applied, the semantic-Hook mechanism for one-sided two-candidate gap detection shows no attributed utility: activations occur only on contract-negative questions, improvements only on Hook-negative no-op runs, while accuracy declines and Hook cost rises sharply. Stop unchanged; revisit only with activation-attributed accuracy gains on valid positives at acceptable cost against a matched control.", "applicability": "Delimits semantic-Hook selectivity/utility claims for one-sided evidence-gap detection in this evaluation setting; a legitimate revisit needs valid positive probes with differential, cost-justified benefit.", "evidence_refs": ["candidate_review"], "experience_type": "experiment_direction"}]}`
- causal attribution: TODO
- route discipline: TODO
- evidence fidelity: TODO
- actionability: TODO
- applicability: TODO
- overall: TODO
- notes: TODO

## Anchor 稳定性

- `candidate_reject_hook_false_positive_scope`: type_sets=`[['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction'], ['student_capability', 'experiment_direction']]`, type_stable=`True`; semantic stability: TODO
