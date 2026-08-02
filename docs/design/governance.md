# 治理与审计

本文记录研究系统当前确认的治理边界。统一术语以仓库根目录 `CONTEXT.md` 为准；本文
只描述权限、证据与确定性决策原则。

## 当前原则

- Student Agent 只接触任务问题、Model Context、已注册 Tool Result 和 Hook 明确注入的内容。
- 只有 Task Evaluation 直接读取 golden answer；Student Agent、Intervention Executor 和
  Mechanism Compiler 不得直接访问，Teacher Role 只通过声明的 Resource 获得所需 Evidence。
- Reviewer 通过只读 Resource 检查 Evaluation、Trajectory、Trial 或 Candidate，不直接
  修改 Candidate Workspace 或 Template Version Store。
- Hypothesis Researcher 提出可证伪假设，Intervention Executor 执行 Trial，Evidence
  Reviewer 判断证据，Mechanism Distiller 形成 Mechanism Spec，Mechanism Compiler
  只编译已有 Evidence 支持的 Mechanism Spec。
- Teacher Role 只产生 Recommendation、Verdict 或 Finding；Evolution Controller 与
  Promotion Gate 保有最终确定性 Decision 权限。
- `fixed` 组件由父版本定义，模型不得修改或新建 fixed 组件。
- Model 调用、Intervention、Template File Edit、Validation、Review 与 Promotion 或
  Rejection 都必须留下可追踪 Artifact、Event 或 Record。

## 当前限制

- Template Version Store 是单进程、单写者模型，没有并发锁和完整跨文件事务恢复。
- Evolution Run 恢复仍允许覆盖少量执行配置；比较有效性依赖 Artifact 中保存的 Model、
  Dataset、Template 和执行 provenance。
- Evidence Review 与 Mechanism Conformance Evaluation 提供工程证据，不构成形式化证明。
- 旧持久化 schema 只在显式读取边界兼容；恢复后产生的新 Record 与 Event 使用当前名称。

尚未确认的治理决策应写入 [open-decisions.md](open-decisions.md)。
