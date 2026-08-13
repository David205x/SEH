# todo.md 改造复核与 20260808_slice01–05 轨迹分析

复核日期：2026-08-09
复核对象：`docs/audits/todo.md` 全部改造项 + `runs/evolution/20260808_slice01`…`slice05`
对照基线：`runs/evolution/20260807_qwen3-8b`（改造前同一 dataset / 同一 incumbent）

> 说明：本机所有 Python 环境均未安装 pytest，单元测试未能实际执行；测试部分只做了用例清单与断言内容的静态核对。

---

## 一、结论摘要

改动本身是正确的、与 todo 规格一致的，并且在轨迹上可验证地解决了 todo 想解决的两个症状：

1. Selector 不再把预算浪费在同一个 example 的其他 prefix 上；
2. Evidence Reviewer 从「每 Trial 一次」变成「每批次一次」。

但这 5 次实验同时暴露了两个**改造没有覆盖、且被改造放大了的**新问题，它们是本轮实验实际成本的主要来源：

- **P1 批次被无关 example 填充**：Selector 在 Failure Analyst 的 refs 用尽后，直接按 rollout 文件顺序取 example，不做失败相关性过滤。slice04 的第一批里有 2 个 example 在 incumbent 评估中是 `stable_correct`，干预条件根本不可能触发。
- **P2 revision 后重选同一批 assignment，证据逐字相同**：reset 清空 `used_assignments` 后，确定性 Selector 必然重选同一组，导致 slice04 的 rev1–rev5 产出**完全相同**的 coverage，5 轮修订、约 215 万 token、零新增信息，最终以 revision 预算耗尽结束。

净效果：单个 Hypothesis 版本的 loop 成本基本没变（约 40–46 万 token/版本），但**版本数被上述两个问题推高**（基线 1 个版本，slice01 3 个，slice04 6 个）。所以 todo 第七节的验收标准可以判定为达成，但「提高循环效率」这一总目标只部分达成。

---

## 二、逐项核对（todo 一~五）

### §1 Hypothesis 修订与证据重置 —— 已实现，轨迹已验证

`transitions.py:114 on_research_hypothesis` 用白名单重建 `input_refs`（只保留 `rollout_file`/`report_dir`/`failure_artifact`/`hypothesis_artifact`），并把 `trial_count`/`assignment_count`/`used_assignments`/`prior_obligation`/`pending_assignments`/`batch_*` 全部归零。`hypothesis_revision` 累计计数保留。

slice04 实测（每个 revision 的第一批 Evidence Review）：

```
rev0  trial_count=3  reviewer 收到 trial_reviews=3  in_refs trials=[trial_001..003]
rev1  trial_count=3  reviewer 收到 trial_reviews=3  in_refs trials=[trial_001..003]
...   rev2–rev5 同上
```

新版 Evidence Review 完全没有看到旧版 Trial。✅

Researcher 修订期间仍能读到旧 Trial：`research_hypothesis` 在 rev≥1 时的 `input_refs` 含 `trial_001..005` + `trial_review_001..005_artifact` + `coverage_summary_artifact`；提交后这些 ref 在 `select_trial` 上消失。✅

### §2 Reviewer→Researcher 修订交接 —— 已实现，效果最好的一项

Prompt 按 todo 要求加了 `Observed failure:` / `Required revision:` / `Must preserve:` / `Claim limit:` 四段稳定结构。轨迹里 Reviewer 严格照做，例如 slice04 第二次 revise：

> Observed failure: post_tool positive distinct examples 1/2 … Required revision: narrow activation_condition/applicability to the exercised boundary … Must preserve: one supported positive … Claim limit: no longer claim 2-example coverage …

Researcher 侧同样生效：**6 个 revision 的 Researcher 调用里，`get_trial_evidence` / `get_trial_event` 调用次数全部为 0**（只有 rev0 的初始研究调用了 `get_student_trajectory`）。这正是 todo「反馈足够时直接提交，不重复审判 Evidence」的目标。✅

代价：因为完全不看 Trial，修订实际上只是措辞收紧。slice04 rev2→rev5 的 `activation_condition` 只在同义改写（"ends without the attribute value, cut off mid-sentence" → "ends mid-sentence, visibly truncated, without containing" → …），`fork_phase` 与实质门控从未变化，所以证据也不可能变化。这不是 prompt 的错，是 P2 的表现。

### §3 分层批次取样 —— 已实现，是本轮最有效的修复

配置链路完整：`config/runtime.yaml` → `_EVOLUTION_CONTROL_FIELDS` 白名单 → `evolution_control_values()` 的 `trial_batch_size <= max_trials_per_hypothesis` 校验 → `EvolutionControlConfig` 的 `__post_init__` 同名校验（默认 3）。

选择顺序按 fresh example → new replicate → phase-compatible fallback 三段实现（`intervention_effects.py:161-202`），批内 `example_id` 唯一，数量 `min(batch_size, remaining_trial, remaining_assignment)`。

**基线 vs 现在的直接对比**（这是本次改造最硬的证据）：

| | 20260807 基线 | 20260808 slice01–05 |
|---|---|---|
| Failure Analyst 给出的 refs | 4 个，全为不同 example | 2–4 个 |
| 实际选中的 assignment | `5a72a00d/r000/5`, `5ae0d91e/r000/5`, **`5ae0d91e/r000/10`** | 每批 example_id 全不相同 |
| 3–5 个 Trial 的 distinct example | 2 | 5 |

基线在**有 4 个不同 example 可选**的情况下仍然把第 3 个 Trial 花在了 `5ae0d91e` 的另一个 prefix 上 —— 这正是 todo §3 要消灭的行为，现在消灭了。✅

批次形状：5 个 slice 全部是 `3 → 2`。第二批的 2 不是候选耗尽，而是 `remaining_trial_budget = 5 - 3 = 2` 的正确夹取（rollout 文件有 225 条记录 / 75 个 example，候选池远未耗尽）。

未被这 5 次实验覆盖的路径：replicate 批（pass 2）、prefix fallback（pass 3）、`unsuitable_assignment`、`exhausted` —— 因为 fresh example 一直充足，这几条分支一次都没走到，只有单元测试覆盖。

规格偏差（无害）：`selection_mode` 取值为 `fresh`/`reuse`，todo 写的是 fresh/replicate；`transitions.py:175` 的白名单与之一致。

### §4 批次执行与 Review 节奏 —— 已实现，且超出 todo（改为并行）

todo 说「不要求引入并行执行」，实现选择了并行：`InterventionEffects.execute_batch()` 用 `asyncio.Semaphore(rollout_workers)` 并发跑整批，`_on_execute_trial_batch()` 把整批作为一次持久化转移提交，并保留了顺序单条路径（`pending_assignments is None` 时回落）。断点续跑靠 `intervention_trial_checkpoints/<fingerprint>` + 输入一致性校验。

Evidence Reviewer 调用次数：

| 运行 | 版本数 | Trial 数 | Evidence Review 次数 | Trial/Review |
|---|---|---|---|---|
| 20260807 基线 | 1 | 3 | 3 | 1.0 |
| slice01 | 3 | 15 | 6 | 2.5 |
| slice02/03/05 | 2 | 10 | 4 | 2.5 |
| slice04 | 6 | 30 | 12 | 2.5 |

**Evidence Reviewer 调用次数 = 批次数，与 Trial 数解耦。**✅ 每版本固定 2 次。

Trial Review 复用也在轨迹里验证：每个版本第二批的 `input_refs` 带 `trial_review_001..003_artifact`，只有 004/005 是新跑的。✅

墙钟收益（并行带来的）：基线单 Trial 的 `execute_trial` 约 33–53 s；现在 3 条一批约 52–77 s、2 条一批约 16–41 s。等效单 Trial 时间约降到 1/2.5。

一个需要注意的记账变化：基线的 `execute_trial`/`review_evidence` effect usage **没有把 Trial Reviewer 的 token 计入**（基线三个 `trial_reviews/*.json` 里合计 78k token 未进入任何 effect usage）。现在计入了。所以「review token 变贵了」的表象里有一部分是记账修正，不是真实回归：

| | Evidence Reviewer / Trial | Trial Reviewer / Trial |
|---|---|---|
| 基线 | ~14k | ~26k（未记账） |
| slice05 | ~7k | ~25k |

Evidence Reviewer 的每 Trial 成本确实腰斩，这是批次化的真实收益；Trial Reviewer 仍是 review 侧的成本主体（todo 明确要求保持每 Trial 一次，符合预期）。

### §5 测试要求 —— 用例齐备（未执行）

- Selector：`tests/evolution/test_intervention_effects.py` 有 11 个用例，覆盖 fresh 优先、reuse 分散、prefix fallback 不被误认为新 replicate、双预算夹取、确定性可复现、`exhausted`、并行批次顺序与 checkpoint 复用。
- Controller：`tests/evolution/test_control.py`（38 个用例）含 `test_calls_evidence_reviewer_once_for_a_three_trial_batch`、`test_batch_assignments_execute_in_order_before_one_review`、`test_parallel_trial_batch_commits_once_in_assignment_order`、`test_selected_batch_cannot_exceed_remaining_trial_budget`、`test_empty_batch_reselects_without_evidence_review`、`test_revised_hypothesis_resets_batch_and_old_evidence_refs`。
- Prompt：`tests/evolution/research/roles/test_prompting.py` 有 `test_evidence_revision_prompt_preserves_existing_protocol`、`test_researcher_revision_prompt_uses_feedback_before_trials`。

对照 todo §5 清单，唯一没有对应用例的是「Researcher revision 期间仍能通过现有工具访问旧 Trial」的端到端断言（reset 侧有，读取侧没有）。轨迹里这一点是成立的。

---

## 三、5 次实验暴露的问题

### P1（严重）批次被 incumbent 已答对的 example 填充

`list_rollout_references()`（`research/intervention/prefix.py:94`）返回 rollout 文件里**全部**记录，按文件顺序，无任何失败相关性过滤。Selector 的候选来源是 `[*failure.evidence_refs, *list_rollout_references(...)]`，所以 Analyst refs 用尽后就是「文件前几条」。

slice04 实测（Analyst 只给了同一个 example 的两个 replicate）：

| 批内位置 | example | rollout 文件序号 | incumbent 评估结果 |
|---|---|---|---|
| 1 | 5adf8d5b | 29 | 失败（Analyst 指定的目标） |
| 2 | 5abd9054 | 0 | **stable_correct, score=1** |
| 3 | 5a8b6375 | 1 | unstable |
| 4 | 5a81ff1d | 2 | 失败 |
| 5 | 5ab70446 | 3 | **stable_correct, score=1** |

结果：`intervention_applied_count` 在 slice04 是 0/5（rev0）和 1/5（rev1–5），其余全是 `correct_non_intervention`。Reviewer 的 `positive distinct examples ≥ 2` 因此几乎不可达。

这个问题与 Analyst 输出的 distinct example 数强相关：

| 运行 | Analyst refs 的 distinct example 数 | 首批中来自 Analyst 的比例 | 5 Trial 的 positive | 结局 |
|---|---|---|---|---|
| slice01 | 4 | 3/3 | 2 | rev2 → ready_to_distill |
| slice02 | 2 | 2/3 | 2 | rev1 → ready_to_distill |
| slice05 | 2 | 2/3 | 2 | rev1 → ready_to_distill |
| slice04 | **1** | 1/3 | 0–1 | rev5 → 预算耗尽，无产出 |

`FailureDirection` 契约（`roles/contracts.py:31`）只要求 `evidence_refs` 有 2–4 条且互不相同，**不要求 example 互不相同**，所以 slice04 的 `['5adf8d5b/r000','5adf8d5b/r002']` 是合法输出。

### P2（严重）revision 后重选同一批，证据逐字相同

reset 把 `used_assignments` 清空，Selector 是确定性的，候选顺序来自冻结输入 —— 于是新版本必然重选同一组 assignment。slice04 rev1–rev5 的 assignment 完全相同（`5adf8d5b/r000/5, 5abd9054/r000/5, 5a8b6375/r000/5` + `5a81ff1d/r000/5, 5ab70446/r000/5`），产出的 coverage 也完全相同：

```
rev1 batch2  pos=1/1ex neg=4/4ex unc=0 applied=1  unmet=['post_tool positive distinct examples: 1/2']  → revise
rev2 batch2  pos=1/1ex neg=4/4ex unc=0 applied=1  unmet=['post_tool positive distinct examples: 1/2']  → revise
rev3 batch2  （同上）→ revise
rev4 batch2  （同上）→ revise
rev5 batch2  （同上）→ revise
```

5 轮修订、约 215 万 token、零新增信息。Reviewer 每次都指出同一个缺口，而这个缺口**在这 5 个 example 上是结构性不可满足的**，Controller 也没有任何机制让它去换 example。

reset 语义本身符合 todo §1，问题在于 todo 没有规定「新版本应当在新的 example 上取证」。

### P3（中等）批次几何强制在第二批 `conclusion_required`

`max_trials_per_hypothesis=5`、`trial_batch_size=3` ⇒ 恒定 `3+2`，第二批结束时 `trials_remaining=0`，`_evidence_review_budget()` 置 `conclusion_required=True`。于是**每个版本的第二次 Evidence Review 都不允许 `continue`**，必须在 revise/reject/ready_to_distill 里选。

轨迹里 12 次「第二批」review 全部 `conclusion_required=true`；Reviewer 明确写过「continue and ready_to_distill forbidden; revise is the only supported terminal decision」。

副作用：在证据已经达标（`default_requirements_met=true`）时 Reviewer 仍会选 revise，而下一版本证据逐字相同后又改判 ready_to_distill：

- slice05：rev0 batch2 met=True → **revise**；rev1 batch2 证据相同 met=True → ready_to_distill
- slice01：rev1 batch2 met=True → **revise**；rev2 batch2 证据相同 met=True → ready_to_distill

即 slice01 和 slice05 各有 1 个完整版本（约 43 万 token）是纯 Reviewer 判定抖动的成本，没有任何证据变化在支撑那次 revise。

### P4（次要）两个预算不再对齐

Trial 预算先耗尽时 `assignments_remaining=10`（`max_trial_assignments=15` vs `max_trials_per_hypothesis=5`）。assignment 预算在当前配置下永远不是约束。

### P5（次要）新的默认配置没有被这 5 次实验验证

5 次运行都用 `run.json` 里克隆下来的 `control_config`，其中**没有** `trial_batch_size` 字段（走 dataclass 默认 3），且 `max_trials_per_hypothesis=5` 是改造前的旧值。`config/runtime.yaml` 现在的新默认是 `max_trials_per_hypothesis: 10`，批次会是 `3+3+3+1` —— 尾批只有 1 条，却要对 10 个 Trial 做一次完整聚合 Review。这个形状没有被跑过。

### P6（次要）Researcher 会话跨 revision 累积

slice04 的 Researcher transcript 长度 12 → 19 → 24 → 29 → 32 → 37 轮，每次 revision 都在同一 session 上重读全部历史；且 6 次里有 5 次 `submit_intervention_hypothesis` 调了 2 遍（首次提交被契约校验打回）。单次 revision 5.8–12.5 万 token。

---

## 四、建议（按性价比排序）

1. **给候选池加失败相关性过滤（治 P1）。** Analyst refs 之后的尾部候选不应是文件顺序，而应排除 incumbent 评估中 `stable_correct` 的 example —— `per_example.jsonl` 已经通过 `report_dir` 在 `input_refs` 里了。同时把 `FailureDirection` 契约收紧为「至少 `trial_batch_size` 个不同 `example_id`」。
2. **revision 不要重置 `used_assignments`（治 P2）。** 保留一个 direction 级的 `tested_examples`，让新版本在新的 example 上取证；`trial_count` / Trial refs / Coverage 仍按 todo §1 归零。这与「新版证据从零累计」不冲突，只是不让 Selector 原地打转。
3. **加一个廉价的停滞守卫（治 P2 的最坏情况）。** 若新版本的 `coverage_summary` 与上一版本逐字相同，直接终止该研究方向（reject / 换 failure focus），不再消耗 revision 预算。仅这一条就能把 slice04 从 256 万 token 压到约 90 万。
4. **调整批次几何（治 P3）。** 要求 `max_trials_per_hypothesis >= 2 * trial_batch_size + 1`，或让 `conclusion_required` 在「剩余不足一批」且「coverage 未达标」时才置真，避免 Reviewer 恰好在第一次看到完整 coverage 的那一批被强制终结。同时把 `trial_batch_size` 告知 Reviewer，让它知道 `continue` 能换来多少 Trial。
5. **对齐 `max_trial_assignments` 与 `max_trials_per_hypothesis`**（P4），并跑一次 `max_trials_per_hypothesis: 10` 的 smoke run 验证 `3+3+3+1` 形状（P5）。
6. 补两个测试：Researcher revision 期间可读旧 Trial 的端到端断言；replicate 批 / prefix fallback 的集成级验证（目前只有单元测试，5 次实验一次都没走到）。

---

## 五、验收标准逐条判定（todo §7）

| 验收标准 | 判定 | 依据 |
|---|---|---|
| 初始批次覆盖 `trial_batch_size` 个不同 `example_id` | ✅ | 5/5 slice 首批为 3 个不同 example |
| same-example replicate 不再优先于未选 example | ✅ | 基线 `5ae0d91e/r000/10` 类选择消失；slice04 跳过 Analyst 的第二个同 example replicate |
| 批内 Trial 全部处理完才调用 Evidence Reviewer | ✅ | `_on_execute_trial_batch` 单次提交；轨迹每批 1 次 review |
| Evidence Reviewer 次数与批次数一致 | ✅ | 恒为 2 次/版本，Trial 数 5 |
| revision 后新版证据从零累计，旧 Trial 仅修订阶段可读 | ✅ | rev≥1 首批 reviewer 只收到 3 条；`research_hypothesis` 仍带 trial_001..005 |
| Reviewer 的 `revise` 输出能直接指导字段级修订 | ✅ | 四段结构落地；Researcher 6/6 次零 Trial 工具调用完成修订 |
| Selector / Controller 相同输入可复现 | ✅（但是本轮问题的成因） | slice04 rev1–5 逐字相同的 assignment 与 coverage 既证明了确定性，也暴露了 P2 |

todo 列出的验收标准全部达成。但「提高 Intervention 实验的有效覆盖和循环效率」这个总目标只部分达成：**覆盖的广度上去了，覆盖的有效性没有**（`intervention_applied_count` 常为 1/5），而广度的代价被 revision 重复放大。P1 + P2 + P3 是下一轮该处理的对象。
