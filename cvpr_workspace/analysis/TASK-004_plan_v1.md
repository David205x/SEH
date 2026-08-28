# TASK-004 Plan v1

## 1. 当前状态

- TASK-004 已执行并通过任务级验收，当前状态为 `accepted`。
- 已完成 Controller 全链路 route inventory，覆盖 15 个 `WorkKind`、15 个 completed transition handler、17 个路由组、63 个审计分支和原实现中的 20 个显式终止点。
- 已完成 reject、revise、accept、promotion、Candidate rejection、path-local budget terminal、work failure、retry、resume 和 replay 的责任归属盘点。
- 已建立 `provisional`、`settled_positive`、`settled_negative`、`invalid_indeterminate` 四类审计 taxonomy；该 taxonomy 在 TASK-004 中只是对真实代码的审计映射，尚不是运行时代码合同。
- 已完成 H1/H2 semantic-diff audit，结论为“局部实现缺口，不构成需要返回 `cvpr-goal` 的实质语义冲突”。
- 已生成机器可读路由矩阵、语义审计报告、可重复静态检查和测试执行摘要。
- TASK-004 没有修改 H1/H2 Reviewer decision、Gate、routing、Evaluator 或正式评测协议，也没有修改研究主体实现。
- 静态 route inventory 检查已通过。
- 锁定 Python 环境未安装可选的 `pytest` 模块；该失败尝试已保留，随后使用标准库 `unittest` 运行同一个 Controller 测试文件，40 项测试全部通过。
- TASK-004 的全部产物都标记为 `development_check_only`，不能支持 H1/H2/H3 Claim 或 Goal 验收。

## 2. 任务意图

TASK-004 的目的是在实现 H3 experience lifecycle 之前，先确定当前 Controller 中“什么结果由谁产生、失败后返回哪里、何时只是临时反馈、何时已经形成可结算结果”。它针对的是以下问题：

- Controller 的 route 语义分散在 transition、effect、policy、journal、Candidate Attempt journal 和角色输出合同中，缺少统一、可复查的 route-to-obligation 基线。
- 当前很多终态只能从自然语言 `complete_reason`、payload 计数或 Candidate Attempt 状态推断，不能直接作为 H3 的 settled trajectory 输入。
- promotion 容易被误认为唯一结算点，但 Candidate rejection、not-distillable、预算耗尽和执行无效状态同样需要被区分记录。
- 在开始修改 lineage 和 settlement 代码前，必须先确认当前 H1/H2 机制语义是否与 G-001 冲突，避免执行阶段静默改变上游 Goal。

TASK-004 涉及的 Goal 原文如下。

### H1 原文

> 在持久化 Candidate 物化前，冻结真实 Student Prefix 上的 matched no-op 与不可部署 soft intervention 证据能够预测 downstream Candidate effect，并在预算匹配下提高 useful Candidate yield、减少无效完整评估。

TASK-004 对 H1 的作用是核对 Trial、Evidence Review、Mechanism Distillation、Compiler 和 Candidate Evaluation 的先后顺序与责任边界，确认当前开发流程没有把 Candidate-first evaluation 偷换成 pre-materialization evidence，也明确当前尚缺正式 matched two-arm、frozen Gate、blind compilation 和 rejected bypass 协议。

### H2A 原文

> 对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。

TASK-004 对 H2A 的作用是核对 Hook Feasibility 与 Conformance 的现有能力边界，确认当前实现没有用最终 Candidate accuracy 替代职责级 realizability，同时明确现有 phase-oriented feasibility 尚未覆盖正式五职责 prediction/label 协议。

### H2B 原文

> 基于逐职责 realizability 证据在 reject、simplify、deterministic lowering 与 ownership reassignment 之间进行 adaptive routing，相对固定 ownership 策略能够提高可实现且有用的 Candidate 产出并减少浪费。

TASK-004 对 H2B 的作用是盘点 evidence、mechanism、implementation 三类 obligation 的实际上游责任，确认现有定向回流没有把不同失败层合并；同时明确四类正式 routing control 尚未实现。

### H3 原文

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

TASK-004 对 H3 的作用是确定“已结算轨迹”目前实际由哪些 route、verdict、Candidate Attempt 和 artifact 构成，为后续 TASK-005 的 first-class lineage/settlement contract 和 STAGE-002 的 experience lifecycle 提供事实基线。

## 3. 实施思路

TASK-004 采用“先盘点事实，再判断语义，不修改机制”的实施逻辑。

### 3.1 建立路由事实表

以 Controller 的 durable work 为主轴，逐项跟踪：

1. 当前 work 接收什么 effect/role output；
2. 哪个 decision、status、budget 或 error 触发分支；
3. 下一 work 或 run terminal 是什么；
4. 谁对下一步负责；
5. revision obligation 来自哪个 typed output 字段；
6. 该结果属于 provisional、正向结算、负向结算还是 invalid/indeterminate。

该盘点同时覆盖 Controller 自身的初始化、失败重试、显式恢复、中断恢复、软预算暂停和 agenda drain，避免只检查 `transitions.py` 的正常路径。

### 3.2 区分嵌套生命周期

审计不把 Controller Run 完成当作唯一终态。逻辑上区分：

- work attempt 是否完成或失败；
- Candidate Attempt 是否 pending、accepted 或 rejected；
- research attempt 是否因 revision、not-distillable 或预算终止；
- generation 是否因 promotion 推进；
- Controller Run 是否暂停或完成。

因此，一个 Candidate 可以已经形成 `settled_negative`，同时 Controller 继续启动新的 research attempt。

### 3.3 审计 H1/H2 语义差异

将代码事实分别与 H1、H2A、H2B 的 Goal 原文比较，只允许得出三类结论：

- 一致；
- PLAN 已覆盖的局部实现缺口；
- 必须返回 `cvpr-goal` 的实质冲突。

本任务最终得到第二类结论，没有发现需要修改 Goal 的实质冲突。

### 3.4 建立回归护栏

静态检查从源码 AST 和稳定源码标记重新读取 `WorkKind`、handler、transition 和 terminal 数量，并与机器可读矩阵交叉核对。这样后续代码增加或删除 route 时，旧矩阵不能继续静默通过。

现有 Controller 行为测试用于核对 inventory 对 retry/resume、Candidate reject/promote、Conformance 和 targeted revision 的理解是否与真实行为一致。

## 4. 计划实现

以下代码层级计划已经执行完成。

### 4.1 新增路由覆盖矩阵

文件：`cvpr_workspace/analysis/stage_001_route_coverage_matrix.json`

- 保存任务、阶段、证据范围和 development base commit。
- 保存四类 settlement taxonomy 的审计定义。
- 保存 lineage 与 role identity 的当前字段和缺失字段。
- 为每个 Controller work kind 保存 route group。
- 为每个 branch 保存稳定 ID、触发条件、下一步、责任义务、结算分类和源码定位。

### 4.2 新增 H1/H2 语义审计

文件：`cvpr_workspace/analysis/stage_001_h1_h2_semantic_diff_audit.md`

- 记录 H1/H2 一致部分和局部缺口。
- 记录 lineage、role identity、replay、retry、settlement 和 budget 边界。
- 明确 TASK-004 产物不能支持正式 Claim。

### 4.3 新增可重复检查

文件：`cvpr_workspace/checks/check_stage_001_route_inventory.py`

- 从 `domain.py` 解析 `WorkKind`。
- 从 `transitions.py` 解析 completed handler、transition call 和 terminal site。
- 核对矩阵是否完整覆盖全部 work kind 和辅助路由。
- 核对 branch ID、字段、settlement 分类和源码 marker。
- 核对语义审计报告包含明确的非 Claim 边界和差异结论。
- 输出 `cvpr_workspace/analysis/stage_001_route_inventory_check.json`。

### 4.4 保存测试与执行证据

文件：`cvpr_workspace/analysis/stage_001_test_execution_summary.json`

- 保存缺少 `pytest` 模块的失败尝试。
- 保存标准库 `unittest` 的替代执行命令和 40/40 通过结果。

### 4.5 更新执行期状态

文件：

- `.cvpr/tasks.jsonl`
- `.cvpr/runs.jsonl`
- `.cvpr/state.yaml`
- `cvpr_workspace/入口清单.yaml`

修改内容：

- 追加 TASK-004 的 started 和 accepted 事件；
- 追加静态检查、失败 pytest 尝试和成功 unittest Run；
- 登记稳定手动检查入口；
- 将 `last_accepted_task_id` 更新为 `TASK-004`。

