# Adapter Harness

## 文档职责

本文档说明 Adapter Harness 的定位、角色结构、权限边界、记忆策略和 Soft-to-Hard Hardening 思路。

Adapter Harness 服务于离线适配阶段的外部强模型。它不进入最终部署系统，也不应成为最终实时推理路径的一部分。

Actor 侧运行机制见 `actor-harness.md`。Patch 如何提交、审计、评估、接受和版本化，见 `evolution-protocol.md`。数据可见性和审计规则见 `governance.md`。

## Adapter Harness 定位

Adapter Harness 的目标不是替 Actor 解题，而是帮助发现、验证并硬化适合 Actor 的外部结构。

它在离线适配阶段可以：

- 观察 Actor Rollout；
- 分析失败模式；
- 在受控接口下提出非题目相关的局部干预；
- 调用 Prefix-Fork 比较不同后续轨迹；
- 总结稳定有效的干预模式；
- 将有效模式编译为 Registry Extension Patch；
- 触发 Audit 与 Controlled Evaluation。

Adapter Harness 的产物不是一次性的答案，而是可审计、可版本化、可回滚的 Actor Harness 改进。

## 离线适配阶段

本文档中的“离线适配阶段”指：不处于最终部署系统的实时推理路径中，但可以运行实验、回放轨迹、执行 Prefix-Fork、评估候选 Patch 的阶段。

在该阶段，外部强模型可以参与分析和适配；在最终部署阶段，外部强模型必须退出。

## 统一 Agent，多角色状态

第一阶段 Adapter 暂定为一个统一 Agent，而不是多个独立 Agent。

它通过显式角色状态切换不同职责、上下文、工具和权限。核心角色包括：

1. Critic；
2. Intervention；
3. Compiler。

这种设计的重点不是模拟组织结构，而是让同一个外部强模型在不同阶段受到不同信息边界和权限约束。

## 实验标识与日志

Adapter Harness 应维护可审计日志，用于追溯角色切换、工具调用、干预提交、Prefix-Fork、Patch 提交和评估结果。

这里的日志不是要求每个事件都记录同一组完整字段。不同事件可以有不同的最小字段，但日志整体应能追溯：

- 事件发生时的角色；
- 所属 Harness Version；
- 所属数据划分和可见性边界；
- 所属实验层级；
- 操作输入的摘要；
- 操作输出的摘要；
- 操作是否成功；
- 是否产生干预、Patch 或评估结果。

实验层级建议区分以下标识：

- `harness_iteration_id`：一次 Harness 迭代，从某个已接受 Harness Version 出发，包含若干 Rollout、分析、干预、Patch 尝试和评估，结束于 Patch 被接受、拒绝或本轮不提交 Patch。
- `rollout_session_id`：某个样本在某个 Harness Version 下的一次 Actor 轨迹。Intervention 和 Prefix-Fork 应绑定到具体 Rollout Session。
- `patch_attempt_id`：某次具体 Patch 的提交、审计、评估和接受/拒绝过程。该标识更偏向 `evolution-protocol.md`，但 Adapter 日志需要能够引用它。

这三个标识分别对应版本迭代、单条轨迹和单次 Patch 尝试，不应混用为一个笼统的 round。

## 通用控制面

Adapter Harness 需要具备基础控制面，用于读取当前状态、管理角色、提交干预、调用受控实验工具，以及提交 Patch。

具体工具集合不在本文档中固定，可以随实现演化。第一阶段只需要表达出以下能力：

- 读取当前角色和权限边界；
- 切换角色；
- 读取当前 Harness 配置和 Registry；
- 读取 Changelog、Patch Log 或评估摘要；
- 调用 Prefix-Fork 等受控实验工具；
- 提交 Soft Guidance 或 Soft Repair；
- 提交 Harness Modification Proposal；
- 提交 Patch；
- 维护 Adapter Memory。

部分状态可以直接写入每一步 Prompt 中，例如当前角色、当前 Harness Version、当前数据划分和禁止事项，不一定都需要工具化。

控制面不代表 Adapter 可以绕过治理边界直接修改 Actor Runtime。

## Critic 角色

Critic 用于观察 Actor Rollout 和当前 Harness，分析失败模式、筛选轨迹、发现可改进方向。

本文档中的 Experience Set 指允许 Adapter 进行 label-visible 失败分析的开发经验集。完整的数据划分和可见性定义见 `evaluation.md` 与 `governance.md`。

Critic 主要处理：

- Actor-only Rollout；
- 当前 Harness 配置；
- Registry 当前状态；
- 历史 Patch；
- Changelog；
- Evaluation Summary。

Critic 可以：

- 在 Experience Set 上读取完整 Actor Trajectory；
- 在 Experience Set 上读取 Golden Answer；
- 编写脚本或规则筛选轨迹；
- 统计失败模式；
- 分析高频输出结构或工具调用格式问题；
- 分析当前 Harness Gap；
- 形成抽象改进意见；
- 通过 Role Handoff Packet 传递非题目级信息。

Critic 不得：

- 将具体题目文本写入长期 Memory；
- 将 Golden Answer 写入长期 Memory；
- 将具体文档内容、实体、答案路径传给 Intervention 或 Compiler；
- 直接修改 Harness；
- 直接提交 Patch。

Critic 的输出第一阶段不强制固定 schema，但建议记录：

- failure pattern；
- 涉及的大致样本数量；
- 关联的 Actor 行为缺陷；
- 可能的 Harness Gap；
- 可能的 Intervention 方向；
- 可能的 Hardening Target；
- 风险或不确定性。

这些字段是推荐格式，不是硬约束。

本文档中如无特别说明，schema 问题指 Actor 输出、Action 或 Tool Call 不符合约定结构，导致 parser、validator 或 tool wrapper 无法处理的问题。为避免歧义，后续优先称为“输出结构或工具调用格式问题”。

## Intervention 角色

Intervention 是离线适配阶段的局部干预角色。

它会在 Actor Rollout 的受控接口处被激活，对当前 Actor 行为进行非题目相关的局部审阅、修复或指导。

Intervention 的目标不是替 Actor 做题，而是探索：

- 哪类高层级指导能让小模型表现更好；
- 哪类常见执行错误可以安全修复；
- 哪类局部约束值得硬化；
- 哪些 Prefix 适合进行 fork 比较。

### 允许行为

Intervention 可以：

- 查看当前 Hook 上下文；
- 查看当前 Actor State 摘要；
- 调用 Prefix-Fork 工具；
- 做 pass@k over guidance；
- 做 pass@k over actor sampling；
- 提交局部指导；
- 提交局部评审决定；
- 审阅工具调用格式；
- 对非内容型 schema 或调用错误进行自动补正；
- 提出 Harness Modification Proposal。

第一阶段默认不允许 Intervention 直接调用内容型检索工具。是否允许 Intervention 调用 Actor 的检索工具属于后续未决事项；若未来允许，也应通过受控 Tool Proxy 限制为诊断、复现或格式检查，不能让 Intervention 自行探索证据路径并把结果传给 Actor。

### 禁止行为

Intervention 在提交给 Actor 的指导、修复或评审中，不得包含题目相关内容。

禁止内容包括：

- 具体 search query；
- 具体候选答案；
- 具体桥接实体；
- 具体文档 ID；
- 具体证据缺口；
- “应该打开第几个结果”这类题目相关动作；
- 能让 Actor 直接靠外部强模型提示完成任务的信息。

Intervention 也不得直接修改 Actor Core Loop、State Manager 核心逻辑或 Evaluator。

### 允许的 Soft Guidance

允许给 Actor 的指导应停留在行为层、格式层或过程层，而不是题目内容层。

例如：

- 当前证据不足，不建议直接回答；
- 请检查工具调用参数是否符合 schema；
- 请避免把未验证内容写入最终答案；
- 请在回答前确认多个证据是否一致；
- 当前存在 premature answer 风险；
- 当前输出格式可能无法被 parser 解析；
- 当前需要继续使用 Actor 可用工具验证；
- 当前应避免重复搜索相同内容。

这些指导不能包含具体查询词、实体、答案线索或证据路径。

### Soft Repair

Intervention 可以修复类似调用错误的问题，以避免轨迹长期卡在某一处。

但修复必须满足一个核心约束：

> 可以修复调用形式，不能变更输入参数的语义内容。

允许的修复包括：

- JSON 外层括号缺失；
- 字段名轻微错误；
- 字段类型可安全转换；
- 多余自然语言包裹合法 JSON；
- 工具名大小写或别名错误；
- action 格式稳定但不完全匹配 schema；
- 缺少非语义默认字段。

不允许的修复包括：

- 替 Actor 填写具体 query；
- 替 Actor 填写实体；
- 替 Actor 填写文档 ID；
- 替 Actor 修改搜索目标；
- 替 Actor 改写会影响题目求解路径的工具参数；
- 替 Actor 补全答案内容。

如果某类调用错误高频出现，应记录为 Hardening 候选，而不是长期依赖 Intervention 临时修复。

可能的 Hardening 方向包括：

- schema normalizer；
- tool-call validator；
- parser repair；
- retry policy；
- prompt instruction；
- default field filler；
- pre-tool self-check。

原则是：Intervention 可以推进非内容型执行障碍，但不能替 Actor 完成题目内容决策。

## Prefix-Fork Tool

Prefix-Fork 是 Adapter Harness 的离线实验工具。

它是 rollout-local 的：必须绑定到一个 `rollout_session_id`，并且只能从该 Actor 轨迹中已经存在的某个 Prefix 或 Runtime State Snapshot 出发，重新生成后续轨迹。

Prefix-Fork 用于比较当前轨迹后续路径中的不同指导、不同采样或局部 Harness 变化效果。它不是跨样本的小型评估器，也不应用于同时尝试多个问题对应的轨迹。

Prefix-Fork 主要用于：

- 比较不同 Soft Guidance；
- 评估同一 Guidance 下 Actor 采样稳定性；
- 观察某类干预是否改变失败路径；
- 验证某个 Harness Extension 是否改善局部行为；
- 分析 Failure Transition；
- 为 Hardening 提供证据。

Prefix-Fork 不进入最终部署系统的实时推理路径。Actor Harness 只需要提供可复现状态、Trace 和 Snapshot 支持；何时 fork、如何比较 fork 结果，属于 Adapter Harness 和评估流程的职责。

如果需要在多个样本上比较 Patch 效果，应使用 Controlled Evaluation，而不是扩大 Prefix-Fork 的职责。

## Compiler 角色

Compiler 负责将有效的 Soft Intervention、Failure Pattern、Soft Repair、Prefix-Fork 结果和 Critic 意见转化为结构化 Harness Patch。

Compiler 不是简单总结者，而是将“软经验”硬化为 Registry Extension 的角色。

Compiler 可以：

- 读取抽象 Failure Pattern；
- 读取 Intervention 统计；
- 读取 Prefix-Fork 对比结果；
- 读取 pass@k 结果；
- 读取 Patch History；
- 新增或修改 Registry Extension；
- 提交 Patch；
- 触发评估；
- 根据需要切换回 Critic 或 Intervention。

Compiler 不得：

- 读取 Experience Set 中具体题目级信息；
- 读取 Golden Answer；
- 修改 Evaluator；
- 修改 Actor Core Loop；
- 修改数据划分；
- 将题目级信息写入 Harness；
- 让最终 Harness 调用外部强模型。

Intervention 可以提出 Harness Modification Proposal，但正式 Patch Submit 由 Compiler 完成。

这样可以保持：

- Intervention 聚焦局部行为探索；
- Compiler 聚焦结构化硬化；
- Patch Log 更清晰；
- 角色权限更可审计。

## Adapter Memory

Adapter Memory 用于保存跨轮次的抽象经验，但不得保存题目级信息。

不允许保存：

- 具体问题文本；
- Golden Answer；
- 具体实体；
- 具体文档 ID；
- 具体检索结果内容；
- 能反推出答案的轨迹摘要；
- 样本级 shortcut；
- 数据集中特定样本模式。

允许保存：

- 抽象 Failure Pattern；
- 高频输出结构或工具调用格式问题；
- 工具调用格式缺陷；
- 小模型行为倾向；
- 非题目相关的 Prompt 缺陷；
- 通用 Harness Gap；
- Patch 效果趋势；
- Registry Extension 经验；
- 评估指标变化；
- 审计发现。

Adapter Memory 的目标是帮助系统积累结构性经验，而不是积累题目答案或样本路径。

## Role Handoff

角色切换时，不允许直接携带完整上下文。

Critic、Intervention 和 Compiler 之间应通过 Handoff Packet 传递抽象信息。Handoff Packet 应主动移除 case-level 信息，只保留 general pattern 信息。

建议 Handoff Packet 包含：

- handoff id；
- from role；
- to role；
- harness iteration id；
- rollout session id；
- harness version；
- allowed summary；
- failure patterns；
- proposed intervention patterns；
- proposed patch directions；
- forbidden case references removed；
- audit notes。

Handoff Packet 应经过自动审计，检查是否包含题目级信息。

## Soft-to-Hard Hardening 标准

一个 Soft Intervention、Soft Repair 或 Failure Pattern 不应因为单次有效就被硬化。

建议满足以下条件后，再进入 Patch 候选：

- 重复出现；
- 在多个样本或多个 Prefix 上出现；
- pass@k over guidance 显示该指导有效；
- pass@k over actor sampling 显示效果稳定；
- 能抽象成通用 Registry Extension；
- 不依赖具体题目内容；
- 在 Visible-ID Eval Set 上不退化；
- 在 Blind-OOD Eval Set 上不明显退化；
- Audit 未发现泄漏或 shortcut；
- Patch 影响范围可解释、可回滚。

可以概括为：

```text
重复出现 + pass@k 有效 + validation 通过 + regression 不退化
```

## 与 Actor Harness 的边界

Adapter Harness 可以观察和实验，但不能绕过 Actor Harness 的稳定边界。

Adapter 不得：

- 直接修改 Actor Core Loop；
- 直接修改 State Manager 核心逻辑；
- 直接修改 Evaluator；
- 修改数据划分；
- 修改 Golden Answer；
- 绕过 Audit；
- 让最终 Actor Harness 调用外部强模型；
- 把题目级信息写入 Registry Extension 或 Adapter Memory。

Adapter 发现的有效改进必须通过 Registry Extension Patch 进入 Actor Harness，并经过 Audit、Controlled Evaluation 和 Harness Version Store 版本化。

## 第一阶段简化假设

第一阶段 Adapter Harness 采用以下简化假设：

- 使用一个统一外部强模型 Agent；
- 通过角色状态区分 Critic、Intervention、Compiler；
- Role Handoff 只传递抽象信息；
- Intervention 只允许非题目相关的 Soft Guidance 和 Soft Repair；
- Soft Repair 只能修复调用形式，不能变更输入参数语义；
- Prefix-Fork 只用于离线适配和分析；
- Compiler 是唯一正式提交 Patch 的角色；
- Patch 接受前必须经过 Audit 和 Controlled Evaluation；
- 最终部署系统不包含 Adapter Harness。

## 未决事项

以下事项仍需要后续确认或在实现中细化：

- Critic 是否需要固定输出 schema；
- Role Handoff Packet 的精确字段；
- Adapter Memory 的压缩和遗忘策略；
- Soft Repair 的自动审计规则；
- Prefix-Fork 的 pass@k 取值；
- 是否允许 Intervention 通过受控 Tool Proxy 调用 Actor 检索工具；
- Intervention 可见 State 摘要的字段范围；
- Compiler 一次提交一个 Patch 还是允许连续提交多个 Patch；
- Patch 接受决策的具体策略。
