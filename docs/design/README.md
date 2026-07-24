# Search Harness 设计文档

本目录记录 Search Harness 项目的架构、运行机制、治理边界、实验协议和开发路线。它主要表达研究设计与演化方向，部分内容可以先于当前代码实现。

这些文档由原始 `design.md` 拆分而来。拆分的目标是明确各类设计的归属，减少重复，并区分已经确认的设计与仍待决定的事项。

## 推荐阅读顺序

1. [研究思路](research.md)
2. [项目概览](overview.md)
3. [Actor Harness](actor-harness.md)
4. [Adapter Harness](adapter-harness.md)
5. [治理与审计](governance.md)
6. [Harness 进化协议](evolution-protocol.md)
7. [评估体系](evaluation.md)
8. [开发路线](roadmap.md)
9. [未决事项](open-decisions.md)
10. [教师引导的 Harness 机制发现与架构上限](teacher-guided-harness-discovery.md)
11. [Hook 上下文生命周期与学生模型提示实验](hook-context-and-student-prompt-experiments.md)
12. [外部自进化 Harness 静态代码调研](external-self-evolving-harness-static-analysis.md)
13. [Hook 工具委托与提示注入实验](tool-delegation-injection-experiment.md)
14. [分解上下文 Controller Hook 实验](decomposed-context-controller-experiment.md)
15. [Self-Harness 与 Search Harness 对照分析](self-harness-comparison.md)

## 文档职责

- `research.md` 说明研究动机、核心问题、方法假设和第一阶段研究边界。
- `overview.md` 说明系统整体结构、运行闭环、核心不变量和最终部署形态。
- `actor-harness.md` 说明 Actor 侧运行机制。
- `adapter-harness.md` 说明 Adapter 侧离线适配机制。
- `governance.md` 说明数据可见性、权限边界和审计规则。
- `evolution-protocol.md` 说明 Harness Patch 如何从发现、提交、审计、评估到接受。
- `evaluation.md` 说明数据集、指标、评估协议和成功判据。
- `roadmap.md` 说明阶段计划。
- `open-decisions.md` 记录尚未确认的问题。
- `teacher-guided-harness-discovery.md` 记录机制发现条件、当前 Hook 表达上限与外部自进化 Harness 对照研究。
- `hook-context-and-student-prompt-experiments.md` 记录 ModelInput 生命周期、STUDENT 提示对照实验和 Hook 委托主循环调用工具的设计。
- `external-self-evolving-harness-static-analysis.md` 汇总外部自进化 Harness 的固定源码快照、代码级机制与可迁移建议。
- `tool-delegation-injection-experiment.md` 记录动态委托 query、提示注入位置和 Hook 小模型的真实 rollout 对照实验。
- `decomposed-context-controller-experiment.md` 记录带 Hook 模型、状态机和每步上下文重设的分解检索 controller 实现与实验。
- `self-harness-comparison.md` 对照 Self-Harness 论文、公开实现和本项目当前架构，记录可迁移的控制原则、协议设计与研究差异。

## 文档维护原则

- 每项设计应有一个主要归属文档，其他文档通过链接引用。
- 已确认设计与未决事项必须分开记录。
- 代码行为或接口发生变化时，应同步更新对应文档。
- 文档之间出现冲突时，不应静默选择；应先确认正确设计并消除冲突。
- 当前工程实现、代码维护说明与编码规范见 `../manual/` 和仓库根目录的 `AGENTS.md`。
