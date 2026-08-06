# 开发路线

本文只记录当前工程状态与后续独立任务，不承诺具体日期。当前统一术语以仓库根目录
`CONTEXT.md` 为准，已生效决策见 `docs/adr/`。

## 已完成的主体能力

1. 角色无关 Agent/Harness framework、共享 Harness Manifest、Assembly、Tool Execution
   与 Hook Lifecycle。
2. Student 与 Teacher 外部 Harness Template，以及 Native Chat 和 OpenAI Agents SDK
   两种独立 Role Runner 路径。
3. Dataset Rollout、Task Evaluation、Intervention Trial、Evidence Review、Mechanism
   Distillation、Mechanism Compilation 与 Conformance Evaluation。
4. Git-backed Template Version Store、Candidate Attempt Journal、Promotion 与 Rejection。
5. 事件驱动 Evolution Controller、确定性预算与门禁、持久化恢复和统一根 CLI。
6. V1 活动实现删除、Post-removal Normalization、schema v2 命名及非 Visualizer 验收。

## 后续独立工程任务

1. 将专用 Visualizer 作为独立历史程序归档，不要求与当前主体兼容。
2. 按既定大纲分别撰写 Architecture、Reference 与 Guides 正文；不把 `manual_v2/`
   历史正文机械迁移到新目录。

## 后续研究方向

1. 在 Failure Direction 之间进行有界回退，而不只处理最高优先级方向。
2. 比较 Intervention 与最终 Student Mechanism 实现的迁移一致性。
3. 引入独立 validation split，降低 Evolution Set 上反复迭代造成的过拟合。
4. 在证据充分后再扩展 Experience Store、更多 Intervention 分支和候选搜索策略。
