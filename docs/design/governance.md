# 治理与审计

本文记录研究系统当前确认的治理边界。工程接口以 `../manual/` 为准；这里描述的是设计原则。

## 当前原则

- Actor 只接触任务问题、Harness prompt、已注册工具结果和 Hook 明确注入的上下文。
- Evaluation 可以读取 golden answer；Actor、Intervention Worker 与 Coordinator 不得读取。
- Critic 通过只读工具检查评估、轨迹和 Harness，不直接修改插件或版本库。
- Coordinator 负责提出并验证干预机制，Compiler 只把已有证据支持的机制编译为候选事务。
- `fixed` 组件由父版本定义，模型不得修改或新建 fixed 组件。
- 所有模型调用、Hook 修改、候选 patch、验证和接受/拒绝决定应留下可追踪 artifact。

## 当前限制

- Checkpoint Store 是单进程、单写者模型，没有并发锁和完整跨文件事务恢复。
- Evaluation report 尚未绑定 source rollout digest，报告与轨迹必须成对保持不变。
- Evolution 恢复允许覆盖 backend 配置，但当前比较协议没有校验全部模型与 prompt provenance。
- Coordinator 的跨案例证据仍依赖固定守门 Hook 和结构化日志，尚不是形式化证明。

尚未确认的治理决策应写入 [open-decisions.md](open-decisions.md)。
