# TASK-007 真实归因实验经验与预期偏差总结

## 1. 工具设计与本次修正认识

当前 `inspect_experience_evidence` 是一次 Summary Run 内的授权只读视图工具：

- Initial Input 只给模型 `evidence_ref -> compact observation`；
- 程序侧 registry 保存 `evidence_ref -> view -> details(selector, content)`；
- view 只有 `upstream_contract`、`decision_trace`、`candidate_comparison`；
- 一次成功返回最多三条、单条最多 1500 字符、总计最多 4000 字符；
- 工具不接受路径、任意查询或完整 artifact；
- 当前实现允许可选 selector，并设置“最多两次成功读取”，失败调用不计入次数。

真实运行出现 28 次失败工具调用：17 次 selector 猜错、6 次把 selector 当 evidence ref、4 次请求当前 ref 不具备的 view、1 次 selector 数量超限。模型看得见全局 view 枚举，却看不见各 ref 实际有哪些 view 和 selector；Prompt 又说使用 observation 中“exposed”的 selector，但 observation 没有结构化目录。

因此本次确认：不应设置工具 invocation 次数硬限制。归因有时确实需要依次读取 contract、trace 和 comparison，失败后也需要纠正。应限制单次/累计返回证据量、Runner turns 和 token，而不是限制调用次数；同时向模型暴露不含内容的合法 ref/view/selector 目录，并让错误反馈返回可用选项。

## 2. 实验层面的通用经验

1. 决策点 compact observation 对明确 implementation defect 和 aggregate Candidate harm 通常已经足够；不应以 rubric 强制工具调用。
2. 上游成功条件、数据充分性、模型能力和机制内生伤害混在一起时，按需 contract/trace/comparison view 能显著改善归因。
3. 模型能普遍区分 trigger role、route target 和根因；所有无 route target 的 Candidate reject 都没有错误生成 `teacher_work`。
4. route target 目前仍只是弱提示：明确 Compiler query-projection defect 曾完全漏掉 `teacher_work`。
5. `student_capability` 的 Prompt 定义过宽。30 个 Run 中出现 26 次，implementation 和无效输入也会被包装成 capability。
6. 11 个 Run 自动填满三类经验，说明“至多每类一条”被模型理解为值得覆盖 taxonomy，而不是只输出必要经验。
7. `applicability` 总体有效，绝大多数输出会限定任务形状、合同边界或评估条件，而不是无条件泛化。
8. evidence ref 运行时校验有效：全部结构化输出都只引用授权顶层 ref，没有越权引用路径或隐藏 artifact。
9. 工具错误后模型经常能依据错误消息改用正确 ref 和空 selector并成功，说明允许纠错比硬拦截更有益。
10. 工具调用失败率不能直接作为归因质量指标；当前失败主要测到了接口可发现性。
11. 原术语必须完整进入 compact view。只写 Enabled/Disabled 会让模型把 thinking mode 误写成 Hook state。
12. case 文本和 rubric 也是被测系统的一部分；含糊的 `conformant Hook fired` 会诱导模型把 semantic misactivation 称为 conformant activation。
13. 模型主要归因主线在重复 Run 中较稳定；工具路径、是否补充额外类型和局部措辞稳定性明显较弱。
14. 不应把一次合法、可读结构化输出等同于可消费经验；consumer 类型、因果层和事实限定仍需审查。

## 3. 十八个真实案例的经验、可观察推理路径与预期偏差

### 1. Evidence revise：corpus sufficiency 混杂

- 预期经验：Hypothesis 成功条件应以目标证据可检索为前提；实验需分开“未搜索”和“已搜索但无证据”。
- 可观察推理路径：先确认 deferral 和 follow-up search 都执行成功，再对照上游 success condition 与 trial_004 空检索，排除 Reviewer 执行错误，把结论落到上游条件和数据充分性。
- 实际经验：三次均生成正确 `teacher_work` 与 `experiment_direction`；同时生成“空检索后仍从缺失推断不存在”的 `student_capability`。
- 偏差：直接行为观察成立，但从单个 corpus-empty Trial 上升为稳定 capability boundary 过强；原 rubric 把该类型完全禁止也过严，真正应限制的是稳定性和泛化措辞。

### 2. Evidence reject：无 differential effect

- 预期经验：插入 generic verification context 不能仅凭一次 search occurrence 声称有效，必须超过 matched untreated control。
- 可观察推理路径：比较四个 faithful activation 与 control；3/4 不搜索，唯一搜索也在 control 出现，因此 causal claim 被反驳。
- 实际经验：正确生成 Hypothesis obligation、matched-control experiment direction，并补充“generic verification context 未改变搜索行为”的 capability lesson。
- 偏差：原 rubric 完全禁止 capability 偏严；该经验若严格限定为本 context/本行为可以保留，不能泛化成 Student 普遍不可引导。

### 3. Evidence reject：harmful over-trigger

- 预期经验：trigger 必须验证具体 evidence gap，完整证据时不得激活；同时保留 clean falsifier。
- 可观察推理路径：一条 faithful positive 直接 finalized wrong，另一条完整证据 Trial 被误触发并把正确答案变错，因此问题在 Hypothesis trigger，而非 Reviewer。
- 实际经验：生成收紧 trigger 的 `teacher_work` 和要求重复/报告 failure mode 的 `experiment_direction`。
- 偏差：与预期基本一致。

### 4. Hook Feasibility：single-entity negative 不稳定

- 预期经验：Student evaluator 对 single-entity negative 边界不稳定；需要重复验证或缩小支持范围。
- 可观察推理路径：对照冻结 contract 与 thinking-mode × repetition label matrix，排除 parser failure，定位到语义分类稳定性。
- 实际经验：三次稳定生成 capability、Researcher obligation 和 per-case stability experiment direction。
- 偏差：输出把 `thinking_mode enabled/disabled` 写成 Hook enabled/disabled；主要原因是 view 只写 Enabled/Disabled，输入丢失术语，不应只归责 Prompt/模型。

### 5. Mechanism Distiller not-distillable

- 预期经验：Intervention evidence 成立不等于目标 model evaluator 能部署；必须单独验证 surface-overlap negatives。
- 可观察推理路径：先确认 2 positive/2 negative Intervention controls 通过，再读取生产 evaluator probe，观察 both-entities negative 4/4 被误标，隔离 Student evaluator realizability。
- 实际经验：生成 evaluator capability boundary 和“distillation 前必须做 boundary-realizability probe”的 direction。
- 偏差：经验内容与预期一致；工具因隐藏 view/selector 目录先失败两次，属于接口问题。

### 6. Conformance：activation budget 实现错误

- 预期经验：Compiler 必须在 rollout-local state 中执行声明的 activation limit。
- 可观察推理路径：typed finding 已指出预算耗尽后继续 defer；Compiler claim 又错误依赖 runtime phase budget，因此根因是 implementation。
- 实际经验：三次均生成正确 Compiler `teacher_work`；两次额外生成 Candidate behavior 的 `student_capability`。
- 偏差：把 Candidate code 行为命名为 Student capability 是真实类型错误；三次类型不稳定。

### 7. Conformance：classifier passage input 为空

- 预期经验：Compiler 必须把真实 retrieved passages 投影给 classifier；当前证据不能评价 classifier capability。
- 可观察推理路径：四个 mismatch 均显示 trajectory 有 passages、classifier input 却为空，直接隔离到 input assembly。
- 实际经验：正确生成 Compiler obligation；又生成 experiment direction 和“空输入下无法判断”的 capability。
- 偏差：Student capability 不成立，因为模型从未收到合同要求的有效输入；这是最清晰的因果门槛反例。

### 8. Conformance：positive action 未执行

- 预期经验：Compiler 必须把 positive decision 接到 defer、feedback 和 consumed-state 三个动作。
- 可观察推理路径：positive condition 已成立，但 Hook change set 为空，语义判断与动作 wiring 可直接分离。
- 实际经验：只生成 Compiler `teacher_work`，完整列出三个动作义务。
- 偏差：与预期一致。

### 9. Conformance：semantic evaluator 跨 negative/uncertain 边界

- 预期经验：faithful wiring 下，模型 evaluator 无法稳定区分 grounded、no-commitment 和 unsupported-commitment；Distiller 应简化/重构判定。
- 可观察推理路径：对照三值 contract 和四个 mismatch，确认 deterministic action wiring 存在，失败来自 semantic evaluator over-defer。
- 实际经验：三次稳定生成 capability、Distiller obligation 和 boundary-control direction。
- 偏差：核心一致；部分 Teacher lesson 又要求把条件编码到 deterministic action wiring，弱化了“现有 wiring 已正确”的事实。两次工具四次尝试来自隐藏调用目录。

### 10. Conformance：query coverage projection

- 预期经验：Compiler 必须按实体分别投影 coverage，并让 first-only positive condition触发 defer。
- 可观察推理路径：query 明确只含第一实体，implementation 却产生 `both`，根因已完全隔离到 projection。
- 实际经验：文本知道 first-only 不能等于 both，但只输出 `student_capability` 和 `experiment_direction`。
- 偏差：这是最严重的 consumer 偏差；遗漏 route-target Compiler `teacher_work`，并把实现错误投影为 capability。

### 11. Conformance：partial relevance 被当作 decisive fact

- 预期经验：Student evaluator 把 entity profile 等 partial relevance 错当成 decisive cross-entity fact；Distiller 需重构或重新验证边界。
- 可观察推理路径：对照 positive rule 与多个 mismatch，确认 passages 只覆盖一个实体而缺少目标关系，定位 semantic evaluator。
- 实际经验：生成 Distiller obligation 和 Student capability。
- 偏差：总体符合；capability lesson 无证据断言“只有两个记录都存在时才 emit positive”，超过已提供事实。

### 12. Candidate reject：single-passage grounding predicate 内生过严

- 预期经验：机制方向应接受有证据的 cross-passage entailment，并把 false defer、稳定性与成本纳入评估。
- 可观察推理路径：Conformance 已通过，代表 regression 由 literal single-passage rule 直接触发，因此排除 Compiler；aggregate 又显示稳定性和成本伤害。
- 实际经验：三次稳定生成 experiment direction 和“Student 能从分布式/隐式证据正确作答”的 capability。
- 偏差：额外 capability 大体有价值；但一次输出建议接受 prior knowledge，违反上游 contract 中 prior knowledge 不算 grounding 的明确边界，因此原“全部 pass”评价偏松。

### 13. Candidate reject：Hook 只在 explicit negatives 激活

- 预期经验：semantic classifier 的正负边界不可靠，且无 activation-attributed benefit；先验证 precision 再部署。
- 可观察推理路径：对照 negative rules 与 activation cases，发现所有正激活均为 joint/single-entity negatives，改进均来自 no-op variance。
- 实际经验：三次稳定生成 capability 与 activation-stratified experiment direction，没有 teacher work。
- 偏差：内容与预期一致；原 rubric 的“必须调用工具”偏严，因为 Initial Input 已给出 contract-negative、无正向 activation、回归和成本。三次工具失败主要是接口目录不可见。

### 14. Candidate reject：无 activation-attributed utility

- 预期经验：必须按 activation path 判断效用，no-op improvement 不能归功机制；self-assessed evidence gap 不能单独作 gate。
- 可观察推理路径：四个 activation 全部退化或持平，所有 improvements 位于 no-op path，同时有 false defer 和高成本。
- 实际经验：生成 self-assessment capability boundary 和 activation-level cost/benefit direction。
- 偏差：与预期一致。

### 15. Candidate reject：低 precision、低 post-deferral efficacy

- 预期经验：同时检查 trigger precision、后续检索是否改善答案，以及 no-op variance；不能因 faithful implementation 把所有 firing 称为 conformant。
- 可观察推理路径：7 次 activation 中仅 1 次有益、3 次违反 negative rule、4 次最终仍错，aggregate 多为 no-op variance。
- 实际经验：核心 capability/direction 正确。
- 偏差：lesson 自相矛盾地称 7 次为 `contract-conformant activations`；case 输入的 `The conformant Hook fired seven times` 本身有歧义，实验 fixture 与模型共同造成偏差。三次工具尝试全部失败也来自隐藏 view/selector。

### 16. Candidate reject：仅两次 activation 且均 false positive

- 预期经验：没有 activation-driven improvement，所有观察到的 positives 都违反 negative rules，需先修 classification/selectivity。
- 可观察推理路径：对照单实体和 both-entity negative contract、两次 activation outcome 与 no-op improvements。
- 实际经验：生成正确的 experiment direction 和 capability boundary。
- 偏差：一条 direction 把 both-entity-query case 表述为 first-entity-only 条件，局部事实不准确；原 rubric 强制工具调用同样偏严。

### 17. Candidate reject：目标收益被 selectivity harm 与成本抵消

- 预期经验：既保留 target case improvement，也必须设置 out-of-scope precision floor 和 token budget。
- 可观察推理路径：一项归因明确的目标收益对照一项机制导致的 stable-correct regression；aggregate flat 且成本近翻倍。
- 实际经验：生成 natural-language trigger 的 capability boundary和 selectivity/cost direction。
- 偏差：与预期一致，没有因单个成功 case 过度肯定机制。

### 18. Candidate Validation：coverage + defer action 未修复

- 预期经验：Compiler 必须实际修改 coverage projection 与 positive action，并对全部 repair obligations 核对 diff 后再提交。
- 可观察推理路径：validation 显示 resubmission unchanged 且同一缺陷重复，责任层明确为 implementation。
- 实际经验：只生成 Compiler `teacher_work`，没有 capability/direction 扩张。
- 偏差：与预期一致。

## 4. 对原质量结论的修正

原 `quality_audit.md` 的 6 pass / 11 partial / 1 fail 是首轮人工 rubric 打分，应保留为历史结果，但不能直接作为权威比例：

- 工具失败主要测到隐藏调用目录，不能作为归因质量硬失败；
- 部分工具必调 rubric 与 Prompt 的“Initial Input 充分时不调用”冲突；
- 若干 case 输入丢失或混淆术语；
- 个别类型 rubric 过严，但另有 candidate prior-knowledge 输出被原审计放得过松。

当前更可靠的结论是：主要因果主线总体可用，evidence 引用和无 route target 纪律较好；工具可发现性、Student capability 因果门槛、明确 implementation 的 teacher-work 优先级和事实术语保真仍需修订。TASK-007 继续保持 `executed`，尚不验收。

## 5. Sub-agent Prompt/工具审查结论

独立 sub-agent 只读审查确认：

- 27/28 次失败由 ref/view/selector 合法空间不可见直接解释；
- 应取消硬调用次数，让 max turns、token、单次/累计证据量形成自然边界；
- 应在 Model Input 中暴露不含内容的 ref -> view -> selector 目录；
- 非法调用反馈应返回合法选项，支持下一次纠正；
- `student_capability` 必须增加有效输入、faithful implementation 和重复/对照证据门槛；
- 明确 Compiler implementation defect 时，核心类型必须是 `teacher_work`；
- 重新验证前应先修正 case fixture 和 rubric，不能直接沿用首轮比例。
