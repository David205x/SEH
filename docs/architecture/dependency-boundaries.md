# 依赖边界

当前代码在单个 `search_harness` 包内建立可抽取的 Framework 边界，Teacher Template 仍是包外资产。

## 包职责

| 包 | 职责 | 不应拥有的内容 |
| --- | --- | --- |
| `framework` | Agent、Model 协议、Agent Loop、Harness、Manifest、Component 装配、Tool、Trajectory | Student/Teacher 角色、数据集、进化路由、具体 API |
| `integrations` | OpenAI-compatible 与 OpenAI Agents SDK 适配 | 领域决策、模板内容 |
| `datasets` | 数据集配置、加载与统一样本类型 | Agent 执行和判分策略 |
| `evaluation` | Rollout 批处理、任务判分、Teacher Judgment、聚合报告 | 候选晋升和研究路由 |
| `evolution.research` | Teacher Role 协议、资源、干预、机制与角色 Runner | Controller agenda 和 Accepted Version 管理 |
| `evolution.control` | WorkItem、事件日志、effect 调度、transition、预算与 gate | Prompt 内容、模型特定实现 |
| `evolution.versioning` | Template snapshot、校验、Candidate Attempt、Git-backed Version Store | 研究判断与 Evaluation 语义 |
| `runners` | 面向用例的装配入口 | 可复用领域模型和跨流程状态机 |

## 允许的依赖方向

`framework` 位于最内层，只依赖标准库和其自身子包。`integrations` 实现 Framework 协议；`datasets` 与 `evaluation` 使用 Framework 的运行结果；`evolution.research`、`control`、`versioning` 在这些能力上组织进化；`runners` 与 CLI 位于最外层。

模板可以引用 Framework 暴露的 Component API，但 Framework 不反向导入模板。Teacher Role Template 位于 `harness_templates/teacher/<role>/`；共享装配只读取资产，不把它们打包为内核默认值。

## 何时增加抽象

只有出现真实可替换性时才建立共同接口。例如 Student 的 `LoopRunner` 与 Teacher 的 Agents SDK Runner 目前共享 Agent/Harness 概念和装配协议，但调用语义、结构化输出及工具终止行为不同，因此不为了名称对称强行合并为一个 `AgentRunner`。

同理，Role Session、Tool Session 和 Output Session 可以使用角色无关名称与实现，但不要求不同底层在尚未共享生命周期时伪装成同一接口。新抽象应减少重复所有权或稳定依赖方向，而不是预测未来需求。
