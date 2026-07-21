# 未决事项

本文档记录当前尚未确认、但会影响后续实现或实验解释的设计问题。

已确认的设计应移入对应专题文档；本文件只保留待讨论、待验证或待实现时细化的问题。

## Adapter 上下文管理

当前状态：待设计。

Adapter Harness 目前已经定义了 Critic、Intervention、Compiler 三种角色，但还需要进一步设计不同角色看到什么内容、如何维护各自上下文，以及如何避免长轨迹和多轮实验快速消耗上下文窗口。

初步考虑将 Adapter 上下文分为以下层次：

- Global Context：项目目标、当前 Harness Version、核心约束、可用能力和当前阶段任务；
- Role Context：当前角色的职责、权限、禁止事项和输出目标；
- Split-Scoped Context：由数据划分决定的可见信息，例如 Experience Set、Visible-ID Eval Set、Blind-OOD Eval Set 的不同可见性；
- Rollout Context：当前 `rollout_session_id` 下的 Actor 轨迹、当前 prefix、hook、state 摘要和工具调用历史；
- Handoff Context：角色切换时传递的抽象摘要，应移除题目级信息；
- Long-term Adapter Memory：跨 `harness_iteration_id` 保存的抽象经验，不保存题目级信息。

待确认问题：

- 各角色在不同数据划分下具体可见哪些字段；
- Raw Trace、Rollout Summary、Failure Pattern Summary、Handoff Packet、Adapter Memory 之间如何逐级压缩；
- Critic 能否长期保留哪些分析结果；
- Intervention 的上下文窗口中是否允许出现完整历史轨迹，还是只允许当前 prefix 摘要；
- Compiler 是否只能读取抽象 Failure Pattern 和 Patch Evidence，不能读取 case-level 轨迹；
- Handoff Packet 的最小字段和审计规则；
- Adapter Memory 的压缩、遗忘和版本绑定策略；
- 上下文管理应由专门 Context Manager 实现，还是先通过 Prompt 模板和日志约定实现。

设计倾向：

- 不长期向角色 prompt 塞入 raw trace；
- 通过分层摘要逐步减少 case-level 信息；
- 角色切换时只传递经过审计的抽象信息；
- 长期 Memory 只保存非题目级、可迁移的结构性经验；
- 先用简单机制实现，再根据上下文消耗和泄漏风险决定是否引入专门 Context Manager。
