# TASK-004 Plan v2

修订说明：本版本取代 `TASK-004_plan_v1.md` 作为 TASK-004 的当前确认报告；旧版本保留。本版本依据新的持久化汇报规则，在四个固定章节之后新增“盘点结果”。

## 1. 当前状态

- TASK-004 已执行并通过任务级验收，当前状态为 `accepted`。
- 已完成 Controller 全链路 route inventory，覆盖 15 个 `WorkKind`、15 个 completed transition handler、17 个路由组和 63 个审计分支。
- 已盘点原实现中的 20 个显式 `TransitionPlan.complete_reason` 终止点。
- 已覆盖 reject、revise、accept、promotion、Candidate rejection、path-local budget terminal、work failure、retry、resume 和 replay。
- 已建立 `provisional`、`settled_positive`、`settled_negative`、`invalid_indeterminate` 四类审计 taxonomy；TASK-004 只记录真实代码的审计映射，没有把它实现成运行时合同。
- 已完成 H1/H2 semantic-diff audit，结论为“局部实现缺口，不构成需要返回 `cvpr-goal` 的实质语义冲突”。
- 已生成机器可读路由矩阵、H1/H2 语义审计、可重复静态检查、检查结果和测试执行摘要。
- TASK-004 没有修改研究主体代码，没有改变 H1/H2 Reviewer decision、Gate、routing、Evaluator 或正式评测协议。
- 静态 route inventory 检查已通过。
- 锁定 Python 环境未安装 `pytest`；该失败尝试已保存，随后使用标准库 `unittest` 运行同一 Controller 测试文件，40 项测试全部通过。
- TASK-004 产物均属于 `development_check_only`，不能支持 H1/H2/H3 Claim 或 Goal 验收。

## 2. 任务意图

TASK-004 的目的是在开始 H3 experience lifecycle 和 settled trajectory 实现之前，先确定当前 Controller 的真实语义基线：每个结果由谁产生、触发什么路由、下一步返回哪个责任角色、携带什么 revision obligation，以及何时只是 provisional、何时已经形成正向、负向或无效结果。

它针对以下问题：

- route 语义分散在 Controller、transition、effect、policy、Control journal、Candidate Attempt journal 和角色输出合同中，缺少统一的 route-to-obligation 基线；
- 大量终态只能从自然语言 `complete_reason`、payload 计数和 Candidate Attempt 状态拼接推断；
- promotion 容易被误认为唯一结算点，遗漏 Candidate rejection、not-distillable、预算耗尽和执行无效状态；
- 在执行层增加 lineage/settlement 代码前，必须先核对当前实现与 G-001 的 H1/H2 是否存在实质冲突；
- H3 要消费“已结算轨迹”，但当前尚没有明确的 settled trajectory 输入范围。

TASK-004 涉及的 Goal 原文如下。

### H1 原文

> 在持久化 Candidate 物化前，冻结真实 Student Prefix 上的 matched no-op 与不可部署 soft intervention 证据能够预测 downstream Candidate effect，并在预算匹配下提高 useful Candidate yield、减少无效完整评估。

TASK-004 对 H1 的目的，是核对 Trial、Evidence Review、Mechanism Distillation、Compiler、Conformance 和 Candidate Evaluation 的实际先后关系与责任边界，并识别当前实现距离正式 EVAL-H1 尚缺什么。

### H2A 原文

> 对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。

TASK-004 对 H2A 的目的，是核对现有 Hook Feasibility 和 Conformance 是否保持职责级判断与最终 Candidate utility 分离，并确认当前 phase-oriented feasibility 能否直接承担正式五职责 prediction/label。

### H2B 原文

> 基于逐职责 realizability 证据在 reject、simplify、deterministic lowering 与 ownership reassignment 之间进行 adaptive routing，相对固定 ownership 策略能够提高可实现且有用的 Candidate 产出并减少浪费。

TASK-004 对 H2B 的目的，是盘点 evidence、mechanism、implementation 三类义务的真实上游责任，确认定向回流没有把不同失败层合并，并定位正式 routing controls 的缺口。

### H3 原文

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

TASK-004 对 H3 的目的，是回答“已结算轨迹”在当前代码中究竟由哪些 route、verdict、Candidate Attempt 和 artifact 组成，为 TASK-005 的 first-class lineage/settlement contract 和 STAGE-002 的 experience lifecycle 提供事实输入。

## 3. 实施思路

TASK-004 采用“先盘点事实、再建立分类、最后核对 Goal；不修改机制”的实施结构。

### 3.1 以 durable work 为主轴盘点路由

对每个 `WorkKind` 依次记录：

1. 接收的 effect 或 role output；
2. 触发分支的 decision、status、budget 或 error；
3. 下一 work、version advancement、pause 或 run terminal；
4. 下一步责任角色或 deterministic module；
5. revision obligation 的来源字段；
6. 当前结果的审计 settlement 分类；
7. 稳定源码定位和 artifact 来源。

除了正常 transition，还盘点 Controller 的初始化、effect failure、retry、显式 resume、中断恢复、软预算暂停和 agenda drain。

### 3.2 区分嵌套生命周期

逻辑上分别观察：

- physical work attempt；
- logical retry chain；
- Candidate Attempt；
- research attempt；
- generation；
- Controller Run。

一个 Candidate 可以先形成持久 rejection，随后 Controller 返回 evidence、mechanism、implementation 或新 research attempt。因此 Candidate-level `settled_negative` 不要求整个 Run 同时结束。

### 3.3 建立审计 taxonomy

- `provisional`：仍调度后续 trial、review、revision 或 compilation；
- `settled_positive`：已形成耐久正结果，例如 Candidate promotion；
- `settled_negative`：已形成耐久负结果，例如 Candidate rejection、not-distillable 或 path-local budget terminal；
- `invalid_indeterminate`：执行或证据无效，不能解释成科研性负结果。

TASK-004 只在分析产物中使用这些分类，不向运行时注入新状态。

### 3.4 分别审计 H1、H2A 和 H2B

将代码事实与 Goal 原文逐项比较，并把结论限制为：

- 语义一致；
- 已被 PLAN 覆盖的局部实现缺口；
- 必须返回 `cvpr-goal` 的实质冲突。

任何正式协议尚未实现的事实都记录为缺口，不把开发流程近似描述为正式 H1/H2 能力。

### 3.5 建立可重复检查

通过源码 AST 和稳定 marker 核对 `WorkKind`、completed handler、transition、terminal 与 route matrix 的对应关系。后续代码改变 route 时，旧 inventory 必须失败并要求更新，不能静默继续使用。

使用现有 Controller 行为测试交叉核对 inventory 对 retry/resume、Candidate reject/promote、Conformance 和 targeted revision 的理解。

## 4. 计划实现

以下代码层级计划已经执行完成。

### 4.1 路由覆盖矩阵

文件：`cvpr_workspace/analysis/stage_001_route_coverage_matrix.json`

- 保存 development base commit、任务、阶段和证据范围；
- 保存四类审计 settlement taxonomy；
- 保存 lineage 与 role identity 的现有字段和缺失字段；
- 保存 17 个 route group 和 63 个 branch；
- 每个 branch 保存稳定 ID、trigger、next、obligation、settlement 和 source ref。

### 4.2 H1/H2 语义差异审计

文件：`cvpr_workspace/analysis/stage_001_h1_h2_semantic_diff_audit.md`

- 记录 H1/H2 的一致部分；
- 记录正式协议和运行时合同缺口；
- 记录 lineage、role identity、replay、retry、settlement 和 budget 边界；
- 明确本审计不能支持正式 Claim。

### 4.3 可重复 route inventory 检查

文件：`cvpr_workspace/checks/check_stage_001_route_inventory.py`

- 从 `domain.py` 读取 `WorkKind`；
- 从 `transitions.py` 读取 completed handler、直接 transition call 和 terminal site；
- 核对 route group、branch ID、字段、settlement 分类和源码 marker；
- 核对语义审计包含差异结论和非 Claim 边界；
- 输出 `cvpr_workspace/analysis/stage_001_route_inventory_check.json`。

### 4.4 测试执行摘要

文件：`cvpr_workspace/analysis/stage_001_test_execution_summary.json`

- 保存缺少 `pytest` 的失败尝试；
- 保存 `python -m unittest tests.evolution.test_control -v` 的执行结果；
- 保存 40/40 通过以及覆盖的主要行为范围。

### 4.5 执行状态与入口登记

文件：

- `.cvpr/tasks.jsonl`
- `.cvpr/runs.jsonl`
- `.cvpr/state.yaml`
- `cvpr_workspace/入口清单.yaml`

修改内容：

- 追加 TASK-004 started 和 accepted 事件；
- 追加静态检查、失败 pytest 尝试和成功 unittest Run；
- 登记手动 route inventory 检查入口；
- 将 TASK-004 设置为最后一个 accepted 原子任务。

## 5. 盘点结果

### 5.1 盘点范围

| 范围 | 直接检查材料 |
|---|---|
| Controller agenda 与失败恢复 | `search_harness/evolution/control/controller.py` |
| Work/Event/State replay | `search_harness/evolution/control/domain.py` |
| Append-only journal 与 effect 原子写入 | `search_harness/evolution/control/journal.py` |
| 所有 completed work 路由 | `search_harness/evolution/control/transitions.py` |
| work/token pause 与 promotion gate | `search_harness/evolution/control/policies.py` |
| WorkKind 到 effect dispatch | `search_harness/evolution/control/effects.py` |
| Candidate accept/reject transaction | `search_harness/evolution/control/candidate_version_effects.py`、`search_harness/evolution/versioning/` |
| Teacher role decision/obligation 合同 | `search_harness/evolution/research/roles/contracts.py` |
| Role artifact envelope | `search_harness/evolution/research/roles/role_execution.py` |
| Candidate paired outcome digest | `search_harness/evolution/research/candidate_digest.py` |
| 真实行为回归 | `tests/evolution/test_control.py` |
| Goal 与阶段边界 | `.cvpr/goal.yaml`、`.cvpr/plan.yaml#STAGE-001` |

### 5.2 定量盘点

| 观察项 | 盘点结果 | 对判断的影响 |
|---|---:|---|
| `WorkKind` | 15 | 确定 route inventory 的顶层覆盖全集。 |
| `_CompletedTransition` handler | 15 | 与 15 个 `WorkKind` 一一对应，没有发现缺失 completed handler。 |
| route group | 17 | 包含 15 个 work kind、Controller lifecycle 和 research revision helper。 |
| 审计 branch | 63 | 覆盖正常、revision、reject、budget、retry/recovery 和 terminal 分支。 |
| 原实现显式 `complete_reason` site | 20 | 证明终态广泛存在，但主要由自然语言表达，支持后续建立 typed terminal code。 |
| Controller 回归测试 | 40 | 40 项全部通过，支持 inventory 对现有行为的理解；不支持研究效果 Claim。 |

### 5.3 路由和终态事实

| 直接观察事实 | 证据位置 | 据此形成或限制的判断 |
|---|---|---|
| Trial selection 和 execution 位于 Mechanism Distillation、Compiler 与 Candidate Evaluation 之前。 | `transitions.py#on_select_trial`、`#on_execute_trial`、`#on_review_evidence` | 支持“当前开发流程保持 pre-compilation evidence 顺序”；不能据此声称正式 matched no-op/intervention H1 已实现。 |
| Evidence Reviewer 的 `continue` 返回 Selector；`revise/reject` 返回 Hypothesis Researcher；`ready_to_distill` 才进入 Distiller。 | `contracts.py#EvidenceReview`、`transitions.py#on_review_evidence` | 支持 evidence obligation 和 research revision 的责任分离。`reject` 目前不是可冻结的正式 Gate rejection artifact。 |
| Mechanism Distiller 的 `not_distillable` 会完成当前路径，不进入 Candidate 编译。 | `contracts.py#MechanismDistillation`、`transitions.py#on_distill_mechanism` | 支持“promotion 不是唯一有研究意义终态”；该终态当前仍缺 typed settlement contract。 |
| Hook Feasibility 的 `feasible` 进入 Compiler；spec 问题回 Distiller；research 问题回 Researcher。 | `contracts.py#HookFeasibilityReview`、`transitions.py#on_verify_hook_feasibility` | 支持现有 H2 分层责任没有被合并；不能替代正式 recognition/decision/adherence/fallback/parse 五职责协议。 |
| Compiler 能分别请求 evidence、mechanism revision 或报告 implementation blocked。 | `contracts.py#CompilerResult`、`transitions.py#on_compile_candidate` | 支持 Compiler 没有吞并全部失败责任；正式 control condition 仍未建立。 |
| Conformance 汇总能把义务路由到 evidence、mechanism 或 implementation。 | `research/conformance.py`、`transitions.py#on_verify_conformance` | 支持 Candidate 实现保真与机制/证据问题可分层回流。 |
| Candidate Reviewer recommendation 之后仍执行 deterministic safety/effect promotion gate。 | `policies.py#evaluate_promotion`、`transitions.py#on_review_candidate` | 支持 Reviewer `accept` 不能单独越过 validation、runner error、accuracy、effect-goal 或 cost safety。 |
| Candidate revision 先持久 reject Candidate Attempt，再返回对应责任层。 | `candidate_version_effects.py#reject`、`transitions.py#on_reject_candidate` | 支持 Candidate-level negative outcome 可以先结算，而 Controller 继续 research；后续合同必须表达嵌套边界。 |
| Candidate promotion/rejection effect 查询既有 receipt，retry 不重复 accept/reject transaction。 | `candidate_version_effects.py#promotion_result_if_completed`、`#rejection_result_if_completed` | 支持后续 settlement ID 需要与现有 Candidate Attempt 幂等语义对齐。 |
| Work retry 生成确定性新 work ID，但当前没有显式 logical work ID。 | `transitions.py#retry_work` | 支持 TASK-005 增加跨 retry logical identity；也限制当前代码不能直接判断两个 retry 是否属于同一结算来源。 |
| Effect 先原子写入，再提交 `work_completed`；中断恢复会复用已存在 effect。 | `journal.py#ControlArtifactStore.write_effect`、`controller.py#_recover_interrupted_work` | 支持 replay/resume 基础可靠；settlement event 仍需在同一 durable 顺序中接入。 |

### 5.4 Lineage 与 role identity 盘点

| 项目 | 已存在 | 缺失 | 对后续行为的影响 |
|---|---|---|---|
| Generation | payload 与 `version_advanced` | 无独立 episode 边界 | 可以定位 promotion 代次，不能表示 multi-episode。 |
| Research attempt | `research_attempt` 整数 | 稳定 `research_attempt_id` | 不能安全跨 replay/Run 连接 settled attempt。 |
| Candidate attempt | Candidate Attempt journal 的稳定 ID | 与统一 trajectory lineage 的绑定 | Candidate transaction 可追溯，但尚不能直接作为 H3 trajectory record。 |
| Optimizer episode | 无 | `optimizer_episode_id` | H3 的 multi-episode 统计与经验生效点无法正式表达。 |
| Role identity | role ID/version、model provenance、output schema digest、validated input、resource config、template path | base prompt/template content digest、完整 role contract digest、rendered input-view digest | 当前 role artifact 可定位开发调用，但不能直接作为严格 scoped experience identity key。 |

### 5.5 H1/H2 协议盘点

| Goal 部分 | 当前已有事实 | 当前缺口 | 路由结论 |
|---|---|---|---|
| H1 | pre-compilation Trial、Evidence Review、Distillation 与 Candidate gate 层级 | repeated matched no-op/intervention、冻结 Prefix/Selector、frozen Gate、blind compilation、rejected bypass | 局部实现缺口，按 PLAN 返回 STAGE-004 补齐；不修改 Goal。 |
| H2A | phase-oriented Hook Feasibility 和真实 Conformance observation | recognition、decision、adherence、fallback、parse 五职责 prediction 与独立 label | 局部实现缺口，按 PLAN 返回 STAGE-004 补齐；当前结果不能支持 H2A Claim。 |
| H2B | evidence/mechanism/implementation 定向回流 | no-feasibility、always-Student、always-deterministic、adaptive routing 四类公平 control | 局部实现缺口，按 PLAN 返回 STAGE-004 补齐；当前路由不能支持 H2B 效果 Claim。 |

### 5.6 Budget 盘点

- Trial、assignment、Hypothesis revision、Mechanism revision、Compiler revision、Candidate revision 和 generation 都有 path-local budget 路由。
- Controller 的 work/token budget 是 effect 启动前的 soft pause。
- `ControlState` 只聚合 `total_tokens`。
- 当前没有 all-in reservation/commit/refund，也没有统一计入全部 Teacher、Judge、Student/hook、Retriever、experience context 和 full Candidate Evaluation。
- 因此 TASK-004 只把 path-local budget exhaustion 识别为现有终态；正式 hard budget 必须按 PLAN 在 STAGE-005 实现。

### 5.7 测试盘点

- `pytest` 调用失败原因是锁定环境缺少 `pytest` 模块，测试代码未运行，也没有生成 JUnit 文件。
- 使用同一 Python 环境执行 `python -m unittest tests.evolution.test_control -v`。
- 共运行 40 项测试，40 项通过，0 failure，0 error。
- 通过范围包括 retry/resume、中断后 effect 恢复、Candidate reject/promote transaction、Conformance 定向回流、Candidate staging 幂等、promotion gate 和新 research attempt。
- 这些测试只支持 TASK-004 对现有行为的工程盘点，不支持 H1/H2/H3 的科研效果判断。

### 5.8 基于盘点形成的最终判断

- 当前 H1/H2 开发代码与 G-001 的主线没有发现实质语义冲突，因此 TASK-004 不返回 `cvpr-goal`。
- 当前缺口均可定位到已确认 PLAN 的后续阶段：lineage/settlement 属于 STAGE-001，H3 lifecycle 属于 STAGE-002/003，H1/H2 正式协议属于 STAGE-004，hard budget 属于 STAGE-005。
- promotion 不能作为唯一 settled source；Candidate rejection、not-distillable 和 path-local budget terminal 必须进入后续 typed settlement 设计。
- work failure、协议污染和中断无完整 effect 必须保持 `invalid_indeterminate`，不能写成科研负结果。
- TASK-004 可以验收 route inventory 和 semantic audit，但不能验收任何 Goal acceptance criterion。

