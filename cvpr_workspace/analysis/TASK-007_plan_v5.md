# TASK-007 真实归因质量验证方案 v5

## 1. 当前状态

- `experience_summarizer@1` 的五字段输入、四字段草稿、唯一受限证据工具和四层归因 Prompt 已实现。
- 确定性检查与 Evolution 回归已通过，TASK-007 当前状态为 `executed`，尚未验收。
- `.env` 已配置 Teacher API 凭据，`config/runtime.yaml` 的 Teacher 为 `deepseek-v4-flash`、thinking enabled。
- 已定位可复用的 Evidence Review、Hook Feasibility、Mechanism Distillation、Conformance、Candidate Review 和 Candidate Validation 负向 artifact。
- 尚未调用真实 API 验证 Experience Summarizer 的工具选择、根因归属、经验类型、适用边界和重复稳定性。

## 2. 任务意图

本次验证使用 Goal 前已有 Run 的真实负向 artifact 构造 Experience Summarizer 输入样本，检查模型能否在只看到紧凑决策点和按需裁剪证据时，正确区分触发决策、Controller route target 与实际根因，并输出有证据、可执行且不过度泛化的 Experience Draft。

涉及的 Goal H3 原文为：

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

本次结果用于验证 TASK-007 总结角色的实际归因质量和决定是否需要修订 Prompt/输入 view，不作为 H3 方法效果、正式 baseline 或 Goal 验收证据。

## 3. 实施思路

### 3.1 真实 artifact 样本组合

建立 18 个不同负向决策样本：

- 3 个 Evidence Reviewer 样本：一个受 corpus sufficiency 混杂的 `revise`，两个 causal claim 被真实 Trial 反驳的 `reject`；
- 1 个 Hook Feasibility `needs_research_revision` 样本：区分冻结 contract 与 Student evaluator 稳定性；
- 1 个 Mechanism Distiller `not_distillable` 样本：区分 Intervention evidence 成立与 Student model 无法稳定实现决策边界；
- 6 个 Conformance 样本：覆盖 activation budget、空 passage projection、动作未执行、query/passage 语义分类错误和 evaluator 边界错误；
- 6 个 Candidate Reviewer `reject` 样本：覆盖机制 predicate 内生伤害、Hook false positive、无 attribution benefit、成本过高和 Student rollout variance；
- 1 个 Candidate Validation rejection 样本：验证明确 implementation defect 是否路由为 Compiler teacher work。

其中 6 个归因混杂或风险较高的 anchor 样本各运行 3 次，其余样本各运行 1 次，共 30 个 Experience Summarizer Run。每次 Run 使用独立输出文件，不覆盖已有 artifact。

### 3.2 输入构造

每个样本保存：

- 原始负向 decision artifact 和直接上游 artifact 引用；
- 五字段 Initial Input；
- 按 evidence ref 授权的 `upstream_contract`、`decision_trace` 或 `candidate_comparison` 紧凑内容；
- 预先标注的主要因果层、允许的经验类型、禁止的误归因、工具使用预期和必须保留的适用边界。

输入构造只抽取 typed output、deterministic summary、少量 finding/trial/probe matrix 和代表性 Candidate 对照。完整 Prompt、transcript、conversation、Model Input、reasoning、resource config、完整 rollout/report、workspace/code、hash/digest 不进入模型可见输入或工具结果。

### 3.3 真实 API 运行

复用 `NativeChatRoleRunner` 和 `harness_templates/teacher/experience_summarizer/`。验证入口按样本顺序执行并限制并发，保存每次完整 Role Artifact、模型输出、工具调用、usage 和失败信息。

运行只调用 Teacher API；不调用 Student、Retriever、Judge 或 Evolution Controller，不改变历史 Run。

### 3.4 归因质量判定

每个 Run 按运行前冻结的 case rubric 核对：

- `causal attribution`：是否把问题放在正确的当前决策、上游设计、implementation、Student capability 或数据/环境层；
- `route discipline`：是否错误地把 trigger role 或 route target 当作根因，是否在无合理 route target 时生成 `teacher_work`；
- `type correctness`：经验类型是否与证据支持的结论一致；
- `evidence fidelity`：lesson 是否由引用证据支持，是否虚构 artifact 中不存在的事实；
- `actionability`：lesson 是否包含下一次可执行义务，而非复述 verdict；
- `applicability`：是否限制在证据支持的条件内；
- `tool restraint`：紧凑输入充分时是否避免工具，存在混杂时是否读取正确 view，且不进行无关调用；
- `stability`：anchor 样本的重复输出是否保持相同主要因果层和经验类型。

每项记录 `pass`、`partial` 或 `fail` 及直接证据。任何失败样本都保留，不通过删除样本或只报告最好重复来提高结果。

## 4. 计划实现

### 4.1 `cvpr_workspace/configs/task_007_attribution_cases.json`

- 固化 18 个 case 的来源 artifact、五字段输入、授权 evidence views、重复次数和验收 rubric。
- 每个 view 内容保留原始 source ref，便于从生成输入回查 artifact。

### 4.2 `cvpr_workspace/entrypoints/run_task_007_attribution_validation.py`

- 校验 case 配置并调用 `build_experience_summary_request`。
- 使用 `NativeChatRoleRunner` 执行 `experience_summarizer@1`。
- 为每次重复保存独立 Role Artifact，并生成只汇总状态、output、tool calls 与 usage 的运行清单。
- 已存在输出目录时拒绝覆盖。

### 4.3 `cvpr_workspace/analysis/analyze_task_007_attribution_validation.py`

- 读取冻结 rubric 与全部运行 artifact。
- 确定性检查结构、证据引用、类型、工具 view、调用次数和失败状态。
- 生成逐 case 审计表，语义归因、可执行性和适用边界由我对照原 artifact 逐项复核并写入同一报告，不使用模型自评替代证据审查。

### 4.4 `cvpr_workspace/入口清单.yaml`

- 登记 TASK-007 真实 API validation 入口、case 配置、输出目录和分析入口。
- 运行范围标记为 `development_check`，明确不能支持 Goal Claim。

### 4.5 运行证据

- API 原始输出保存到 `cvpr_workspace/analysis/task_007_attribution_validation_v1/runs/`。
- 汇总与逐 case 结论保存到 `cvpr_workspace/analysis/task_007_attribution_validation_v1/summary.json` 和 `quality_audit.md`。
- 每次真实运行追加 `.cvpr/runs.jsonl`；完成后更新 TASK-007 的 executed 证据，不在用户确认前标记 accepted。

若结果显示需要修改 Prompt、输入合同或 evidence adapter，本轮只记录问题和证据，先生成新的方案报告并等待批准，不直接修改研究实现。

## 5. 盘点结果

### 5.1 API 与执行入口

- `NativeChatRoleRunner` 已能通过 `.env` 的 Teacher credential 和 `config/runtime.yaml` 的 Teacher profile 执行当前模板、原生工具循环与终态结构化输出。
- 当前配置的 Teacher 是 `deepseek-v4-flash`，thinking enabled；Experience Summarizer 尚无生产专用 role budget，因此验证入口需要显式限制运行并发和输出目录，但不修改生产 Teacher 配置。
- 现有 `experiments/run_role_input_repetitions.py` 能重复 replay 一个持久化 Role Input，但不能把异构负向 artifact 转换为 Experience Summary 的紧凑输入和授权 view，因此需要 TASK-007 专用稳定入口。

### 5.2 真实归因边界

- `review_evidence-054cca1b11f4a49c` 的 `revise` 同时包含成功条件过强与 corpus insufficiency，必须读取上游 contract 和失败 Trial 才能避免归错 Reviewer。
- `verify_hook_feasibility-64ddfe9a2a85e492` 的负向结论由重复 label flip 和负例 false positive 支持，主要归因是 Student evaluator capability/stability，而不是 Hook Feasibility Reviewer。
- `verify_conformance-112c1011c5657e1c` 的 activation budget 违约是明确 implementation defect，紧凑 decision 已接近充分；它适合检验模型是否克制使用工具。
- 多个 Conformance artifact 表面都返回 revise，但一部分是 passage 未注入或动作未执行，另一部分是 Hook-model semantic evaluator 无法遵守 contract；这些样本用于检查 Summarizer 是否区分 deterministic implementation 与 Student-owned classifier capability。
- `review_candidate-9c4407ec7edef219` 的主要问题是 Mechanism predicate 内生过度保守；Compiler 与 Candidate Reviewer 均不是根因。
- 其余 Candidate rejection 同时含 Hook false positive、无 activation-attributed benefit、Student stochastic variation 和高成本，适合检查模型是否形成有限的 Student capability 或 experiment direction，而不是把全部失败压成 Compiler teacher work。
- 历史 artifact 属于 Goal 前开发材料；本次可用于角色行为诊断和 Prompt 修订依据，但不能升级为 H3 正式效果证据。
