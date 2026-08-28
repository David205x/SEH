# TASK-010 Shadow Conformance Replay 实施计划 v1

## 当前状态

- 已完成：Shadow Distiller、Shadow Prompt Researcher 与 Shadow Compiler 已对单 phase、无业务 state 的真实 Artifact 完成联调。
- 已完成：Compiler Candidate 已通过静态、Assembly、完整 Pipeline 与同 rollout lifecycle validation。
- 正在进行：为 `ShadowMechanismSpec` 接入真实 Candidate rollout 与语义 Conformance Review。
- 尚未完成：Shadow Reviewer input contract、Template、可复用 replay effects 适配、独立运行脚本和真实 API 验证。
- 尚未验证：Candidate 在 Distiller 引用的原 Trial 案例上是否忠实实现 frozen decision、defer action、fallback 与 activation limit。

## 任务意图

本任务在全量 Candidate Evaluation 前，使用研究阶段的真实 Trial 案例运行已提交 Candidate，并判断实现是否忠实于 Shadow Mechanism。Reviewer 只消费实际 Candidate 轨迹、参考 Trial observation 与冻结机制，不从静态 Validation 推断语义正确。

本任务服务于 Goal 中以下主张的实现链，但当前少量 Trial replay 不单独构成最终 Claim 证据：

> CLAIM-H2A：对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。

## 实施思路

- 保留正式 `conformance_reviewer@1` 与旧 `MechanismSpec` 输入不变。
- 新增 `shadow_conformance_reviewer@1`，直接接受 `ShadowMechanismSpec`，输出继续使用稳定的 `ConformanceReviewBatch@5`。
- 复用现有 Trial case loader、Candidate replay、Teacher Judge、轨迹投影、逐 Example batch review、checkpoint 与结果聚合。
- 将 Conformance effects 对机制的读取收敛到三个确定性 helper：完整 JSON、effect kind、声明 phase；旧机制与 Shadow 机制各自提供准确值。
- Shadow Prompt 按 guards → Decision/Generation Task → on_success/fallback → activation limit/state 的顺序审查，不把 Hook-model 自报标签当作正确标签。
- 独立脚本从 Shadow Distiller Artifact 读取机制和 Trial files，从 Compiler Artifact 读取 Candidate，从源 Run 读取 Experience Set 与执行配置，在输出目录建立隔离 Version Store 后运行真实 replay 和 Reviewer。

## 计划实现

- 修改 `roles/contracts.py`，增加 `ShadowConformanceReviewerInput` 与角色注册。
- 新增 `harness_templates/teacher/shadow_conformance_reviewer/`，复用紧凑 batch renderer 和稳定输出协议，提供 Shadow Mechanism 专用系统 Prompt。
- 修改 `control/conformance_effects.py`，让现有 effects 接受两种机制并由构造参数选择 Reviewer role；正式默认值保持不变。
- 修改 `config/runtime.yaml`，增加 Shadow Reviewer 独立预算。
- 新增 `experiments/run_shadow_candidate_conformance.py`，完成 Artifact 解析、隔离 Candidate staging、真实 replay、审阅与结果保存。
- 增加合同、Template、机制 helper 和脚本输入组装测试；运行受影响的定向回归。
- 使用 `0827` Shadow Distiller、Prompt Researcher 与 Compiler Artifact 执行真实 Student 和 Teacher API 验证，不修改任何上游产物。

## 盘点结果

- 当前正式 Conformance effects 的 rollout、Evaluation、trajectory projection、checkpoint 和 aggregation 均与旧机制字段无关，可直接复用。
- effects 目前只在 Reviewer Input、effect goal 和 declared phase normalization 三处读取 `MechanismSpec` 专有字段，适合使用局部 helper 扩展，而不需要第二套 replay 实现。
- 当前 `ConformanceReviewerInput.mechanism` 固定为旧 `MechanismSpec`，不能直接接收 Shadow Artifact；强行转换会制造旧协议要求但 Shadow 不提供的冗余字段，因此采用独立 Shadow input contract。
- Distiller Role Artifact 已保存 8 个 Trial file 路径；源 Run `runs/0827_debug` 已保存 Experience Set 和执行配置，能够确定性准备 replay。
- Compiler Candidate Artifact 保存完整 changed files 与 parent digest，可在隔离 Version Store 中重建并验证，不需要修改原始版本库。
