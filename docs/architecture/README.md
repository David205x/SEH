# 架构

本目录描述当前实现的系统边界、主要数据流与依赖方向。术语以[项目语境](../../CONTEXT.md)为准；字段、命令和操作步骤分别放在 [Reference](../reference/README.md) 与 [Guides](../guides/README.md)，避免在架构文档中重复维护。

- [系统上下文](system-overview.md)：系统目标、参与者、运行时与持久化边界。
- [Agent 与 Harness Framework](agent-harness-framework.md)：`Agent = Harness + Model`、装配、生命周期与状态所有权。
- [Evaluation](evaluation.md)：Rollout、静态判分、Teacher Judgment 与聚合。
- [Evolution](evolution.md)：证据驱动闭环、WorkItem 路由、恢复与晋升。
- [依赖边界](dependency-boundaries.md)：包职责与允许的依赖方向。

当前文档只覆盖活动实现。`docs/manual_v1/`、除代码风格外的 `docs/manual_v2/`、`harness_templates/search-o1/` 与实验模板均不是当前架构依据；Visualizer 暂不纳入本轮架构。
