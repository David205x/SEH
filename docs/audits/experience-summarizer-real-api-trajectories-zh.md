# Experience Summarizer 真实 API 轨迹译注

日期：2026-08-26

本文从最终配置的真实 API 验证中选取三条代表轨迹，保留模型看到的决定性输入、关键推理原文和结构化提交，并给出忠实中文翻译。重复的 System Prompt 和大段自我权衡不整段复制；凡有省略均显式标记。完整原始 transcript 以对应 `role.json` 为准。

## 1. Capability：同一语义判断同时出现稳定误判与重复翻转

原始 Artifact：

`runs/experiments/20260826_experience_summarizer_redesign_v5_final_config/hook_model_boundary/rep_02/role.json`

模型看到的决定性 Observation 原文：

```text
subject: Hook model applying one frozen three-label semantic decision at pre_final
expected: trial_...001=positive; trial_...002=negative; trial_...003=negative; trial_...004=positive
observed: 11/16 repeated decisions matched reference; mismatched or unstable conditions:
  ...002/disabled=positive,positive expected negative;
  ...002/enabled=negative,positive expected negative;
  ...003/disabled=positive,positive expected negative
comparison: Same case and model-visible input repeated within each thinking mode; enabled and disabled modes are separate conditions.
conditions: phase=pre_final; thinking_mode varies by row; repetitions=2
validity: reference=confirmed; model_input=confirmed; implementation_fidelity=confirmed; data_environment=not_applicable
open_checks: []
```

中文整理：在 `pre_final` 阶段，让 Hook model 对同一套冻结的三值语义边界作判断。四个案例的参考标签依次为正、负、负、正；16 次直接判断中有 11 次符合参考。关闭 thinking 时，两个应判为负的不同案例都连续两次被判为正；开启 thinking 时，其中一个案例第一次判负、第二次判正。同一 thinking mode 内的重复调用使用相同的模型可见输入，所有参考、输入和实现有效性均已确认。

模型关键推理原文：

```text
So we have consistent errors on repeated valid input:
- case 002/disabled: repeated positive, positive ... expected negative
- case 003/disabled: repeated positive, positive ... expected negative
- case 002/enabled: negative then positive — that's a substantive decision flip ...

[The model repeatedly weighs whether these should be one aggregate item or two items.]

I'll submit two items: one for consistent over-positive mislabeling
(disabled mode, two cases), one for instability/flip on repeated input
(enabled mode). Both cite observation 1.
```

中文翻译：这里同时存在两种可独立成立的限制。第一，关闭 thinking 时出现重复且同方向的误判：参考应为负，但两个不同案例都连续两次被判为正。第二，开启 thinking 时，相同输入在两次调用间从正确的负标签翻转为正标签。模型在“合并为一个偏向正标签的问题”与“按准确性和稳定性拆成两项”之间反复权衡，最终选择拆成两项，且都只引用 Observation 1。

原始提交：

```json
{
  "items": [
    {
      "evaluated_behavior": "Three-label semantic decision at pre_final: labeling of decisive-negative inputs",
      "observed_limitation": "Inputs with reference label negative were labeled positive on both repetitions for two distinct cases in disabled mode; expected negative, observed positive, deviating toward the positive label.",
      "conditions": "phase=pre_final; thinking mode disabled; repetitions=2; two distinct cases with reference label negative",
      "evidence_refs": [1]
    },
    {
      "evaluated_behavior": "Stability of the three-label semantic decision at pre_final on repeated identical input",
      "observed_limitation": "A reference-matching negative on the first repetition flipped to positive on the second repetition of the identical input in enabled mode; expected negative on both repetitions.",
      "conditions": "phase=pre_final; thinking mode enabled; repetitions=2; single case with reference label negative",
      "evidence_refs": [1]
    }
  ]
}
```

中文翻译：

1. 被评估行为：`pre_final` 的三值语义判断对明确负例的标注。观察到的限制：关闭 thinking 时，两个参考标签为负的不同案例均连续两次被判为正，存在稳定的向正标签偏移。
2. 被评估行为：相同输入重复执行 `pre_final` 三值语义判断时的稳定性。观察到的限制：开启 thinking 时，第一次符合参考的负标签在第二次调用中翻转为正标签，而两次参考都应为负。

审阅提示：这次调用第一次耗尽了 4096 token，却没有提交终态工具调用；Runner 追加“尚未提交结构化结果”的续接消息后，第二次调用完成提交。最终结论合理，但拆成一项还是两项仍有粒度波动。

## 2. Direction：Candidate 通过晋升门

原始 Artifact：

`runs/experiments/20260826_experience_summarizer_redesign_v5_final_config/promotion_passed/rep_02/role.json`

模型看到的决定性事实原文：

```text
Candidate Reviewer recommendation=accept; Promotion Gate passed=true.
Aggregate accuracy rose 0.733→0.783 (44→47/60 correct).
The target case changed from stable failure (0/3, one search, memory-committed answers)
to stable correct (3/3, a second targeted search, final answer quoting the retrieved value).
All +3 correct answers came from this target case.
```

中文整理：Candidate Reviewer 接受候选，确定性晋升门也通过。总体准确率由 0.733 上升至 0.783，即 60 条轨迹中由 44 条正确变为 47 条正确。目标案例从 3 次全部失败、仅检索一次并凭记忆作答，变为 3 次全部正确、执行第二次定向检索并引用检索值；新增的 3 条正确轨迹全部来自该目标案例。

模型关键推理原文：

```text
This is a strong, decisive update for the Mechanism Scheme within the tested scope.
The mechanism was implemented faithfully, the target behavior changed as expected,
Candidate Review accepted it, and the deterministic Promotion Gate passed.

However, it is only one observed count-type bridge case. It does not establish
coverage of year/age variants or the entire Failure Direction.
```

中文翻译：在已测试范围内，这是对 Mechanism Scheme 的强且决定性的正向更新。实现忠实，目标行为按预期改变，Candidate Reviewer 接受且确定性晋升门通过。但证据只有一个 count 型桥接案例，不能证明对 year/age 变体或整个 Failure Direction 的覆盖。

原始提交：

```json
{
  "evidence_update": "Decisive support for the Mechanism Scheme within measured scope: the Candidate faithfully implements the one-shot verification-instruction hook, and the target failure mode flipped from stable memory-committed failure (0/3, one search) to stable grounded correct (3/3, second targeted search quoting the retrieved value). Aggregate accuracy rose 0.733→0.783 with all +3 correct from this target case; Promotion Gate passed and Reviewer accepted.",
  "disposition": "Treat the Mechanism Scheme as supported for the tested condition: after a first search identifying only the intermediate entity without the asked terminal numeric value, one appended verification instruction yields an additional targeted search and a grounded final answer. This does not establish coverage of other bridge variants or the full Failure Direction.",
  "revisit_condition": "Changed disposition requires broader or conflicting evidence: replicated runs on additional multi-hop bridge cases spanning count, year, and age variants, a larger sample, or a different harness/baseline; or a failed replication where the one-shot instruction fails to induce a targeted second search.",
  "applicability": "Bounded to the tested baseline_search harness, the multi-hop count bridge question case (single observed example), the one-shot generic verification instruction, and the recorded evaluation run with confirmed implementation fidelity and data environment.",
  "evidence_refs": [1]
}
```

中文翻译：当前 Mechanism Scheme 在测得范围内得到决定性支持：一次性验证提示 Hook 把目标失败从稳定的记忆作答转为稳定的二次定向检索和有证据作答。当前只应把它视为在该单一 count 型案例、当前 `baseline_search` harness 和本次评估环境下受支持；需要更多 count/year/age 案例、其他环境的复现或反例，才能扩大或收窄结论。

## 3. Direction：准确率上升但 Candidate 未通过晋升门

原始 Artifact：

`runs/experiments/20260826_experience_summarizer_redesign_v4_budgeted/promotion_failed/rep_01/role.json`

模型看到的决定性事实原文：

```text
Candidate Reviewer recommendation=revise; Promotion Gate passed=false.
Aggregate accuracy rose 0.733→0.800 (44→48/60 correct).
Paired changes: 4 improved, 1 regressed, 15 unchanged.
The hook classifier fired on essentially every first search result (60 model calls)
and activated on a broad, unstable set including clearly non-numeric questions.
On the "House network" question the appended "do not answer from memory"
instruction caused the Student to refuse, regressing that case 1.0→0.667.
```

中文整理：尽管总体准确率由 0.733 上升至 0.800，Candidate Reviewer 仍要求修订，晋升门未通过。配对变化中有 4 题改善、1 题退化、15 题不变。Hook classifier 几乎对每次首次检索都进行了模型调用，并在明显不是数值问题的案例上激活；在 “House network” 问题中，追加的“不要凭记忆作答”提示导致 Student 拒答，使该题由 1.0 降至 0.667。

模型关键推理原文：

```text
The mechanism, as implemented, is over-broad in its activation ... causing a regression.

This is an implementation failure with a concrete, reusable failure pattern:
the classifier's activation is not selective ... and the instruction causes refusals
on non-numeric questions.

This does not refute the upstream Failure Direction or Research Scheme.
```

中文翻译：当前实现的激活范围过宽并造成退化。这是带有可复用具体模式的实现失败：分类器缺乏选择性，附加提示又会在非数值问题上诱发拒答。它不能反证上游 Failure Direction 或 Research Scheme，只能约束当前 Mechanism Scheme 的激活边界与提示表述。

原始提交：

```json
{
  "evidence_update": "The Candidate instantiation of this Mechanism Scheme failed the deterministic Promotion Gate (passed=false; reviewer=revise). The hook fired on essentially every first search (60/60 calls) and activated on clearly non-numeric questions; on the 'House network' question the appended 'do not answer from memory' instruction made the Student refuse, regressing that case 1.0→0.667. Aggregate accuracy improved 0.733→0.800 and unstable answers dropped 5→3, but the effect is not gate-clean: activation is not selective to numeric-terminal verification.",
  "disposition": "Treat the Mechanism Scheme as not yet established in its implemented form: over-broad activation plus a refusal-inducing appended instruction is not promotable. This does not refute the upstream Failure Direction or Research Scheme; it constrains activation selectivity and instruction phrasing for the mechanism.",
  "revisit_condition": "A revised Candidate whose activation fires only when the asked terminal value is numeric and absent or ambiguous in retrieved passages, whose instruction elicits a targeted follow-up search instead of refusal, and which passes the Promotion Gate with the 'House network' regression eliminated and no new regressions.",
  "applicability": "Bounded to the evaluated workspace: 60-question paired Candidate review on multi-hop bridge questions with numeric terminals, baseline_search harness, post_tool hook patch. Does not generalize to other harnesses, question types, or mechanism designs.",
  "evidence_refs": [1]
}
```

中文翻译：当前 Mechanism Scheme 的这一实现没有通过晋升门。虽然总体准确率提高且不稳定轨迹减少，但 Hook 激活不只覆盖目标的数值终值验证问题，还会在无关问题上诱发拒答，因此当前实现不可晋升。只有新的 Candidate 能把激活限定到“目标数值在检索结果中缺失或含糊”的场景、促使定向检索而非拒答，并消除该退化且通过晋升门，才应改变这一处置结论。

## 4. 重复实验间可见的稳定性边界

最终配置下，Capability 三次调用的事实判断一致：都识别出关闭 thinking 时两个负例稳定误判为正，以及开启 thinking 时一个负例发生重复翻转。差异在于 Draft 粒度：一次合并为一项，另外两次拆成“准确性偏差”和“重复稳定性”两项。

Direction 的通过案例三次均认定 Mechanism Scheme 在单个 count 型目标案例和当前环境内受支持，也都拒绝扩展到 year/age 或整个 Failure Direction；措辞详略有差异，但处置方向没有翻转。

因此，当前真实 API 证据支持“结论方向稳定”，但不支持“Capability Draft 原子拆分完全确定”。若未来需要自动合并，不能仅以 Draft 条数或表面字符串判断重复项，应由确定性 Observation lineage 加语义归并规则处理。
