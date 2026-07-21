# Harness 进化协议

## 文档职责

本文档说明 Harness 如何从一次失败观察或软干预，演化为可审计、可评估、可回滚的 Actor Harness 改进。

本文档连接 `actor-harness.md` 和 `adapter-harness.md`：

- Actor Harness 定义最终系统的运行结构和可变层；
- Adapter Harness 定义外部强模型如何观察、干预和提出改进；
- Evolution Protocol 定义改进如何被提交、审计、评估、接受并写入 Harness Version Store。

数据集划分、指标和评估反馈可见性见 `evaluation.md`。数据泄漏、权限和审计细则见 `governance.md`。

## 进化对象

Harness 进化的对象是 Actor Harness 的 Registry Extension 层。

Harness 自动适配过程不得直接修改：

- Actor Core Loop；
- State Manager 核心逻辑；
- Evaluator；
- 数据划分；
- Golden Answer；
- Registry Loader 核心逻辑；
- 最终部署系统的外部强模型调用边界。

被接受的改进应表现为 Registry Extension 的新增、修改或移除，并由 Harness Version Store 记录版本变化。

## 总体流程

Harness 进化流程如下：

```text
Actor Rollout
→ Critic Analysis
→ Soft Intervention / Soft Repair / Prefix-Fork
→ Hardening Candidate
→ Compiler 提交 Registry Extension Patch
→ Audit
→ Controlled Evaluation
→ Patch Decision
→ Harness Version Store
```

其中：

- `Audit` 使用二态结果：`passed` 或 `rejected`；
- 只有 `passed` 的 Patch 可以进入 Controlled Evaluation；
- `rejected` 的 Patch 不得进入当前 Harness；
- Patch 是否被接受进入 Harness Version Store，由 Critic 根据 Controlled Evaluation 结果、变更内容、轨迹证据和治理约束作出判断；
- 第一版暂不把 Candidate Harness Version 作为独立实现模块。

## 实验层级

进化协议使用以下标识区分不同层级：

- `harness_iteration_id`：一次 Harness 迭代，从某个已接受 Harness Version 出发，包含若干 Rollout、分析、干预、Patch 尝试和评估，结束于 Patch 被接受、拒绝或本轮不提交 Patch。
- `rollout_session_id`：某个样本在某个 Harness Version 下的一次 Actor 轨迹。Intervention 和 Prefix-Fork 应绑定到具体 Rollout Session。
- `patch_attempt_id`：某次具体 Patch 的提交、审计、评估和接受/拒绝过程。

这三个标识分别对应版本迭代、单条轨迹和单次 Patch 尝试，不应混用。

## Hardening Candidate

Hardening Candidate 指可能值得硬化为 Registry Extension Patch 的改进候选。

候选来源包括：

- Critic 发现的 Failure Pattern；
- Intervention 发现的有效 Soft Guidance；
- Soft Repair 中反复出现的输出结构或工具调用格式问题；
- Prefix-Fork 显示稳定有效的局部干预；
- Evaluation 或 Regression 中暴露出的稳定缺陷；
- Adapter Memory 中积累的抽象 Harness Gap。

一个候选不应因为单次成功就被硬化。建议满足以下条件后再进入 Patch 候选：

- 重复出现；
- 在多个样本或多个 Prefix 上出现；
- pass@k over guidance 显示指导有效；
- pass@k over actor sampling 显示效果稳定；
- 能抽象成通用 Registry Extension；
- 不依赖具体题目内容；
- 影响范围可解释；
- 可回滚；
- 没有明显数据泄漏或 shortcut 风险。

可以概括为：

```text
重复出现 + 局部验证有效 + 可抽象 + 可审计 + 可回滚
```

## Patch Submission

正式 Patch 由 Compiler 提交。

Intervention 可以提出 Harness Modification Proposal，但不直接提交正式 Patch。Critic 可以提出 Failure Pattern 和改进方向，但不直接修改 Harness。

Patch 应小步提交。每个 Patch 尽量对应一个明确假设，例如：

- 修复某类稳定输出结构问题；
- 增加某类调用格式检查；
- 增加 before-final-answer review gate；
- 增加 search budget controller；
- 增加 evidence sufficiency checker；
- 调整某个 Registry Extension 的触发条件。

如果一个改进方向包含多个相关改动，可以连续提交多个 Patch，逐步验证。

## Patch 内容要求

Patch 应指向 Registry Extension 层，并遵守统一 Registry Extension Schema。

当前文档阶段不固定完整 Patch Schema。Compiler 提交的 Patch 大致应包含：

- 改动摘要；
- 改动动机；
- Registry Extension 变更内容；
- 预期改善；
- 已知风险；
- 非目标。

Compiler 不负责填写系统生成字段、审计字段或评估字段。

因此，Patch 提交时不应由 Compiler 编写：

- `patch_id`；
- `patch_attempt_id`；
- `parent_harness_version`；
- `proposed_by_role`；
- `constraints`；
- `audit`；
- `evaluation`；
- `decision`。

这些信息应由系统流程补充、检查或填充。

可以将记录分为三层理解：

- Patch Submission：Compiler 提交的改动意图和改动内容；
- Patch Record：系统为该提交补充 ID、来源、父版本、审计结果、评估结果和决策记录；
- Harness Version Store Entry：被接受 Patch 进入版本库后形成的版本记录。

核心原则是：Compiler 只提交改动意图和 Registry Extension 变更；系统负责补充 ID、版本、来源、审计、评估和决策记录。

## Audit

Audit 负责阻止不合规 Patch 进入 Controlled Evaluation。

Audit 检查目标包括：

- 答案泄漏；
- 数据集 shortcut；
- 修改 Evaluator；
- 修改数据划分；
- 修改 Golden Answer；
- 绕过工具调用或审计；
- 让最终 Harness 调用外部强模型；
- 将题目级信息写入 Adapter Memory、Registry Extension、Prompt、Tool、Policy 或 Changelog；
- 通过样本 ID、hash、顺序等方式过拟合。

Audit 可以包含规则审计和模型审计。

规则审计可以检查：

- Patch diff；
- Registry Extension；
- Prompt；
- Tool code；
- Memory；
- Handoff Packet；
- Changelog；
- Config。

模型审计用于发现规则审计难以覆盖的问题，例如 Patch 是否像是在利用数据集分布 shortcut，或某个 Prompt 是否过度贴合 Experience Set。

第一版 Audit 使用二态结果：

- `passed`：未发现阻塞性治理违规，Patch 可以进入 Controlled Evaluation。
- `rejected`：发现阻塞性治理违规，或存在无法自动消解的数据泄漏、越权修改、评估篡改、题目级信息写入等风险，Patch 不得进入当前 Harness。

系统不设置 `pending` 或 `warning` 作为正式 Audit 状态。`pending` 只可作为同步审计内部过程，不进入 Patch 协议。

Audit 可以记录 `audit_notes` 和 `risk_flags`，但这些字段只用于解释和后续分析，不形成第三种状态。

## Controlled Evaluation

Controlled Evaluation 只运行已通过 Audit 的 Patch。

每次 Patch 通过 Audit 后，系统应执行：

- Experience Set 回放或抽样评估；
- Visible-ID Eval Set 评估；
- Blind-OOD Eval Set 评估；
- Regression 检查；
- Cost 统计；
- Trace 统计；
- Patch Result 填充。

第一阶段主指标是正确率。性能提升默认指测试集和评估集上的正确率提升。

Controlled Evaluation 不只看总体正确率，也应关注：

- 已成功样本是否变失败；
- 输出结构或工具调用格式错误是否上升；
- tool call 是否失控；
- token cost 是否大幅上升；
- premature answer 是否增加；
- 搜索次数是否异常增加；
- final answer 格式是否退化。

评估反馈进入 Adapter 前必须经过数据可见性控制。具体反馈可见性规则见 `evaluation.md` 和 `governance.md`。

## Patch Decision

Patch Decision 指决定是否接受 Patch 并写入 Harness Version Store。

第一版中，Patch Decision 归属于 Critic 职责，不新增独立角色。

Critic 可以读取 Patch 变更内容、Audit 结果、Controlled Evaluation 结果、Changelog 和必要的轨迹信息，用于判断是否在该 Patch 形成的新 Harness Version 上继续后续迭代。

Critic 不直接操作底层 Git。Critic 只能通过受控版本决策工具接受或拒绝 Patch，并选择后续迭代使用的 Harness Version；Harness Version Store 的实际写入由系统工具完成。

接受 Patch 的基本条件包括：

- Audit 结果为 `passed`；
- Controlled Evaluation 显示预期指标改善；
- Regression 不出现不可接受退化；
- Cost 增加可接受；
- Trace 统计未显示异常行为；
- Patch 影响范围可解释；
- Patch 可回滚；
- Patch 未引入题目级信息或外部强模型 runtime call。

拒绝 Patch 的原因包括：

- Audit 结果为 `rejected`；
- 评估没有改善或改善不稳定；
- Visible-ID 提升但 Blind-OOD 明显退化；
- Regression 风险过高；
- Cost 显著上升；
- Trace 显示异常策略；
- Patch 过大、难以归因或难以回滚。

Patch Decision 的具体阈值暂不在本文档中固定，应在 `evaluation.md` 或后续实验配置中定义。

## Harness Version Store

被接受的 Patch 应写入 Harness Version Store。

Harness Version Store 是基于 Git 的版本管理工具，用于记录：

- Harness Version；
- Registry Config；
- Registry Extension 内容；
- Patch History；
- Changelog；
- Evaluation Result；
- Audit Notes；
- 可回滚版本。

被接受的 Patch 不应直接修改正在运行的 Runtime，而应生成新的已接受 Harness Version。后续 Rollout 或 Evaluation 由 Experiment Runner 显式选择使用哪个 Harness Version。

选择后续在哪个 Harness Version 上继续迭代，是 Critic 的版本决策职责之一。它既可以选择刚接受的新版本，也可以选择某个先前已接受版本继续后续迭代。

第一版暂不把 Candidate Harness Version 作为独立实现模块。如果后续需要隔离候选版本运行环境，可以再引入 Candidate Staging 或等价机制。

## 选择后续 Harness Version

选择后续 Harness Version 指从 Harness Version Store 中选择一个已接受版本，作为后续 Rollout、分析和 Patch 迭代的基础。

这覆盖了通常意义上的 rollback：当新版本表现不佳时，Critic 可以选择回到某个先前已接受版本继续迭代。

版本选择不应通过手工撤销代码片段实现，而应基于版本记录恢复：

- Registry Config；
- Registry Extension；
- 相关 Changelog；
- 评估记录；
- 审计记录。

选择旧版本继续迭代的常见原因包括：

- 后续评估发现 Regression；
- Blind-OOD 退化；
- 成本异常；
- Trace 显示异常行为；
- 事后 Audit 发现风险；
- 新 Patch 与旧 Extension 发生冲突。

## Changelog

每次 Patch 尝试和 Harness Version 变化都应写入 Changelog。

Changelog 应记录：

- Harness Version；
- Patch ID；
- Patch 摘要；
- 修改的 Registry Extension；
- 触发原因；
- Audit 结果；
- Evaluation 结果；
- 是否接受；
- 是否回滚；
- 后续观察。

Changelog 是 Adapter 重要的长期可见信息，但不应包含题目级内容。

## 日志与可追踪性

Evolution Protocol 需要和 Adapter 可审计日志对齐。

至少应能追踪：

- 哪个 `harness_iteration_id` 产生了某个 Patch；
- 哪些 `rollout_session_id` 支持某个 Hardening Candidate；
- 哪个 `patch_attempt_id` 对应某次 Patch 提交、Audit、Evaluation 和 Decision；
- Patch 进入了哪个 Harness Version；
- 如果被拒绝，或后续选择回到旧版本，原因是什么。

日志不要求每个事件记录同一组完整字段，但应能支持复现、审计和事后分析。

## 与其他文档的边界

- `actor-harness.md` 定义 Actor Runtime、Core Loop、Registry Extension、State Manager 和 Prefix-Fork 支持能力。
- `adapter-harness.md` 定义 Critic、Intervention、Compiler、Soft Guidance、Soft Repair、Prefix-Fork Tool 和 Adapter Memory。
- `governance.md` 定义数据可见性、权限边界和审计细则。
- `evaluation.md` 定义数据集划分、评估指标、阈值和反馈可见性。
- `overview.md` 提供系统整体结构和流程图。

## 未决事项

以下事项仍需要后续确认或在实现中细化：

- Patch Decision 的具体接受阈值；
- `patch_attempt_id` 与 Harness Version Store commit/tag 的映射方式；
- 是否允许 Compiler 连续提交多个相关 Patch；
- 是否需要 Candidate Staging 或 Candidate Harness Version；
- Changelog 的最小字段；
- Regression 阈值；
- Cost 阈值；
- Blind-OOD 退化的容忍范围；
- Patch 冲突检测规则；
- 选择回到旧 Harness Version 后，是否自动阻止同类 Patch 再次提交。
