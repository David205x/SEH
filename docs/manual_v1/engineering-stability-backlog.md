# 工程稳定性修复备忘录

本文记录代码审查中已经确认、但当前阶段暂不打断机制研究的工程稳定性问题。它不是
Evolution 机制设计文档，也不表示这些问题已经修复。实施修复时应补充故障注入或恢复测试，
并同步更新对应 manual。

## 安全与仓库卫生

### S0：本地凭据进入 Git 历史

- 当前 `.env` 被 Git 跟踪，且曾包含非空 Teacher API key。
- 修复时需要轮换已暴露凭据、停止跟踪 `.env`，并根据仓库共享范围决定是否清理 Git 历史。
- 完整 `runs/` 不应作为源码提交；需要保留的实验样例应脱敏、缩减并转为明确 fixture。

## P1：运行与恢复可靠性

### 独立 Compiler CLI 日志路径失效

- `search_harness.adapter.compiler.run._log_payload()` 使用未导入的 `datetime` 与 `UTC`。
- 成功和失败路径都会在写日志时触发 `NameError`，并可能掩盖原始异常。
- 修复验收：覆盖成功、clarification、协议错误和模型异常四类真实 CLI smoke。

### Evaluation report 未绑定 source rollout 内容

- `summary.json` 只保存 `source_file` 路径，没有 rollout digest。
- 原 JSONL 被覆盖后，旧 metrics 可以与新 trajectory 被组合为一份 Critic 证据。
- 修复验收：报告保存 source digest、record count 和复合身份摘要；Critic 加载时重新校验。

### Evolution iteration parent 未在恢复时冻结

- Runner 每次进入循环都读取 checkpoint store 的 latest version，没有以既有
  `iteration_started.parent_version` 恢复当前未完成 iteration。
- 中断期间若同一 store 接受了其他版本，旧阶段 artifact 可能与新 parent 混用。
- 修复验收：模拟中断、外部推进 store、再恢复；Runner 必须继续原 parent 或明确拒绝。

### Resume 允许改变语义配置

- CLI 可以覆盖模型角色、插件路径、步数、重复数等 backend 参数，`.env` 内容变化也没有
  snapshot digest。
- paired validation 当前只比较样本身份和 sampling seed，不比较模型 ID、temperature、
  endpoint、prompt/plugins digest；两侧 seed 都缺失时也会通过。
- 修复验收：把语义配置冻结为 run identity，只允许调整 worker 数、日志级别等执行参数。

### Version Store 接受过程存在跨文件事务窗口

- 当前顺序是写 plugins、创建 Git commit、追加 `versions.jsonl`，随后 IterationSession 再写
  accepted journal event。
- metadata 写入失败或进程突然终止时，Git HEAD、版本索引和 iteration journal 可能不一致；
  append-only JSONL 也没有尾部半行恢复。
- 修复验收：对每个持久化边界做故障注入，并提供启动时 reconciliation 或明确修复命令。

### Compiler attempt 可能遗留孤立 pending transaction

- transaction 在 Compiler 运行前创建，但 Runner 只在 `compiler_completed` 后持久化其身份。
- 进程在 patch、smoke 或日志写入期间终止时，resume 不会发现并关闭该 transaction。
- 修复验收：恢复时按 run metadata 查找未决 transaction，选择复用或显式 reject，不能静默新建。

## P2：审计完整性

- 非 Tool/max-steps 的运行时异常会丢失已经形成的部分 AgentRun 和 trace，且不触发
  `on_error`。
- Coordinator artifact 在模型运行前计算 `revision_source.new_trial_count`，导致该字段不能
 反映实际新增 trial。
- 混合 provider usage schema 时，已有 `total_tokens` 会使只提供 input/output 的调用漏计总量。
- `StateRef.default` 尚未按声明的 `value_type` 校验。

## 与机制研究的边界

以下问题不归入纯工程稳定性修复，应在 Evolution 机制设计中单独处理：

- Critic 多个问题方向如何排序、回退和跨 iteration 记忆；
- Coordinator 如何搜索、复用和淘汰机制假设；
- 选中的 trial 如何与跨案例正向证据强绑定；
- Intervention 证据如何转化为 Compiler 可实现且可泛化的策略；
- 何时把 `inconclusive` 视为继续搜索、切换方向或终止实验。
