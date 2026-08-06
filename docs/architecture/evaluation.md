# Evaluation

Evaluation 将“执行 Student”与“判断结果”分开。Rollout 阶段只产生不可变的运行记录；判分阶段读取记录并生成新的报告，不回写或修补原始轨迹。

## Rollout 层

一个逻辑样本可以执行多个 replicate。每个 replicate 有稳定的 `replicate_id`，重复 Rollout 必须配置 base seed，实际采样 seed 按 replicate index 派生。批处理可以并发执行，但输出保持输入顺序。

每条记录包含：数据集样本、replicate 身份、Harness 来源、可选实验 provenance，以及 `run` 或 `runner_error`。Harness 来源可以是直接模板、Accepted Template Version 或 Pending Candidate Attempt；后两者均由 Version Store 临时物化。

## 判分层

当前任务 Evaluator 是 HotpotQA evaluator：先做规范化精确匹配和 token F1。静态规则无法确定时，可选 Teacher Binary Judge 使用 `TEACHER_*` 模型给出二元判断。Teacher Judgment 是评估能力，不是 Teacher Role，也不参与进化路由。

判分结果按两层聚合：

- per-rollout：每个 replicate 的正确性、静态/Teacher 决策和执行指标。
- per-example：合并同一逻辑样本的 replicate，区分稳定正确、稳定失败和不稳定。

总体 metrics 包含准确率、样本稳定性、错误率、步骤/工具调用以及 token 使用等。Promotion Gate 使用 incumbent 与 candidate 的同口径指标，不能用 Reviewer 的建议替代确定性门禁。

## 可比性约束

- Incumbent Version 与 Candidate Template 必须使用同一个 Evolution Set。
- 评估配置、replicate 数和 seed 策略必须一致。
- Runner error 是执行事实，不能被当作错误答案静默吞掉。
- Teacher Judgment 只补充静态判分，不修改 Student 输出。
- 报告必须携带共享 provenance，避免比较不同模板或配置却误认为同一实验。

命令与文件格式分别见[CLI Reference](../reference/cli.md)和[产物 Schema](../reference/artifact-schemas.md)。
