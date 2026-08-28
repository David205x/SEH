# TASK-005 Plan v1

## 1. 当前状态

- TASK-005 已创建并启动，当前 `.cvpr` 状态为 `running`，尚未验收。
- TASK-005 的输入基线为已验收的 TASK-004 route matrix 和 H1/H2 semantic-diff audit。
- 在用户提出“代码修改前先汇报并等待批准”的新要求到达前，`domain.py` 和 `transitions.py` 已产生部分中间态修改。
- `domain.py` 已初步加入 `logical_work_id`、settlement 分类、trajectory lineage、outcome source、trajectory settlement 和稳定 ID 生成结构。
- `domain.py` 已初步加入 ControlState settlement replay 投影与 work failure artifact/stage 字段。
- `transitions.py` 已初步加入 `TransitionPlan.settlements`、初始 lineage、跨 retry logical identity、新 generation/research attempt ID 和部分 typed terminal settlement。
- Candidate promotion、Candidate rejection、not-distillable 及若干 Trial/Evidence/Compiler/Validation budget terminal 已开始迁移到 typed settlement，但尚未完成端到端接线。
- Controller 尚未把 transition settlement 写入 append-only journal。
- work failure、retry、resume、interruption recovery 与 settlement event 的完整时序尚未实现和核对。
- 尚未新增 TASK-005 专用 development check。
- 尚未更新架构文档和入口清单中的 TASK-005 执行入口。
- 尚未运行修改后的单元测试、route inventory 回归、执行工作区 preflight 或 stage validation。
- 当前核心代码是未验证中间态，不能报告为可用、完成或 accepted。
- 按用户新要求，后续任何实际代码修改必须先由本文件报告状态和方案，并等待用户明确批准。

## 2. 任务意图

TASK-005 的目的是把 TASK-004 中依靠审计推断得到的 lineage、settlement 和 outcome source，升级为 Controller 内 first-class、typed、append-only、可重放的正式代码合同。

它针对以下问题：

- 当前 `generation`、`research_attempt`、`candidate_attempt_id` 分散在 payload 和 Candidate Attempt journal 中，没有统一包含关系。
- 当前不存在稳定的 `optimizer_episode_id` 和 `research_attempt_id`。
- 当前正负终态主要通过自然语言 `complete_reason`、Candidate Attempt 状态和 effect artifact 拼接推断，不能安全驱动 H3 experience settlement。
- retry/resume 可能产生新的 work ID；如果没有 logical identity，H3 后续可能把一次恢复误认成新的独立科研结论。
- work failure、证据污染或中断不能和科研性负结果混为一类。
- settlement 必须绑定 source work、typed verdict、effect/artifact、revision owner 和 obligation，才能在 STAGE-002 中安全生成有 provenance 的 experience。

TASK-005 直接服务于 H3，但同时必须保护 H1/H2 的现有语义。

### H3 原文

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

TASK-005 解决的是这段原文中的前置条件：什么是“已结算轨迹”、typed verdict 如何定位、终态如何分类、provenance 如何绑定、attempt/generation 如何稳定识别。它不实现 experience Store、检索、consumer projection、invalidation 或 H3 正式效果评测。

### H1 原文

> 在持久化 Candidate 物化前，冻结真实 Student Prefix 上的 matched no-op 与不可部署 soft intervention 证据能够预测 downstream Candidate effect，并在预算匹配下提高 useful Candidate yield、减少无效完整评估。

TASK-005 不改变 H1 的 Trial、Evidence Review 或 Gate decision。它只为这些 verdict 增加稳定 source 和 settlement 定位，避免后续 H3 把 provisional Evidence Review 当作 settled Gate 事实。

### H2A 原文

> 对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。

### H2B 原文

> 基于逐职责 realizability 证据在 reject、simplify、deterministic lowering 与 ownership reassignment 之间进行 adaptive routing，相对固定 ownership 策略能够提高可实现且有用的 Candidate 产出并减少浪费。

TASK-005 不补齐 H2 五职责 probe 或四类正式 routing control。它只保存现有 Hook Feasibility、Conformance 和 targeted revision 的 lineage/source，使 STAGE-004 后续新增正式 H2 协议时能复用同一结算合同，而不改变当前 Reviewer 判据。

## 3. 实施思路

TASK-005 采用“显式身份、显式边界、显式来源、append-only replay”的逻辑结构。

### 3.1 定义 lineage 层级

当前提议的包含关系为：

```text
Controller Run
└── optimizer_episode_id
    ├── generation
    │   └── research_attempt_id
    │       └── candidate_attempt_id（Candidate 已物化时）
```

- 一个 Controller Run 对应一个稳定 `optimizer_episode_id`。
- `generation` 保留现有 promotion 后递增的语义。
- 每个 generation 内从 `research_attempt=1` 开始；Candidate 被最终拒绝并重新分析方向时生成新的稳定 `research_attempt_id`。
- Hypothesis revision、Evidence continuation、Mechanism revision 和 Compiler revision 保持在同一个 research attempt 内。
- Candidate 物化后使用现有 Candidate Attempt journal 产生的 `candidate_attempt_id`，不再创建第二套 Candidate 身份。

该定义使 multi-episode 和 multi-generation 是两个可分别统计的维度：episode 对应独立 Controller Run，generation 对应一个 Run 内的 version advancement。

### 3.2 区分 physical work 与 logical work

- `work_id` 标识一次实际执行 attempt。
- `logical_work_id` 标识跨 retry 保持不变的逻辑 work。
- retry 创建新的 `work_id`，但继承 `logical_work_id`。
- 正向和负向科研结算以 logical work 为身份输入，避免 retry 产生重复科研结论。
- work failure 属于具体 physical attempt，因此 `invalid_indeterminate` 记录保留实际 `work_id`，不会覆盖不同失败 attempt。

### 3.3 定义四类 settlement

- `provisional`：后续仍需 trial、review、revision 或 compilation，不能进入跨 generation settled experience。
- `settled_positive`：Candidate 已接受并形成可定位 promotion/version outcome。
- `settled_negative`：Candidate 已拒绝、证据不可蒸馏、局部职责无法满足或 path-local revision budget 已终止。
- `invalid_indeterminate`：work failure、中断无完整 effect、协议或证据无效，不能解释成科研性失败。

不是每个 provisional route 都写 `trajectory_settled` 事件；`provisional` 是合同允许的分类和生命周期判断，只有形成耐久边界的结果才追加 settlement event。

### 3.4 使用 typed terminal code

保留现有 `complete_reason` 作为人类可读说明，同时新增稳定 `terminal_code`，例如：

- `candidate_promoted`
- `candidate_rejected`
- `evidence_not_distillable`
- `no_matching_trial_prefix`
- `compiler_evidence_trial_budget_exhausted`
- `candidate_validation_revision_budget_exhausted`
- `work_attempt_failed`

后续代码只能依据 typed code、classification 和 source contract 判断结算，不从自然语言原因反向猜测。

### 3.5 绑定 outcome source

每个 settlement 保存：

- source `work_id`；
-跨 retry 的 `logical_work_id`；
- `WorkKind`；
- typed verdict；
- effect result 路径；
-相关 artifact refs；
-错误信息；
- revision owner；
- revision obligation。

这样 STAGE-002 的 Curator/summary work 可以从稳定引用读取事实，而不是从 Controller 内存或终端日志推断。

### 3.6 使用 append-only journal 保证 replay

- Controller 在 source work 已经 `completed` 或 `failed` 后追加 `trajectory_settled`。
- `ControlState` replay 根据 settlement ID 重建记录。
- 相同 settlement ID 和相同内容可幂等重放。
- 相同 settlement ID 出现不同内容时 fail fast。
- settlement event 不覆写 Candidate Attempt journal、effect artifact 或历史 ControlEvent。

### 3.7 保持 H1/H2 行为不变

本任务只在既有 route 上增加 lineage 和 settlement 元数据，不改变：

- Evidence Reviewer 的 decision 集合；
- Hook Feasibility decision；
- Candidate Reviewer recommendation；
- promotion safety/effect gate；
- evidence、mechanism、implementation 的定向回流；
- Trial、assignment、revision 和 generation budget 阈值。

## 4. 计划实现

以下为代码层级的完整计划，其中前两项已有部分中间态修改，但仍需在批准后核对和完成。

### 4.1 修改 Control domain

文件：`search_harness/evolution/control/domain.py`

计划修改：

- 为 `WorkItem` 增加可选 `logical_work_id`，旧 journal 缺失时回退到 `work_id`。
- 为 `WorkRecord` 增加 `failure_artifact` 和 `failure_stage` 投影。
- 新增 `SettlementClass`。
- 新增 `TrajectoryLineage`，字段职责如下：
  - `optimizer_episode_id`：定位 Controller Run 对应的 optimizer episode；
  - `generation`：定位 episode 内的版本代次；
  - `research_attempt_id`：定位 generation 内的稳定研究尝试；
  - `candidate_attempt_id`：定位可选的持久 Candidate Attempt。
- 新增 `OutcomeSource`，保存 work、verdict、effect/artifact 和 error provenance。
- 新增 `TrajectorySettlement`，保存 settlement ID、classification、terminal code、lineage、source 和 revision obligation。
- 新增确定性 `optimizer_episode_id`、`research_attempt_id`、`settlement_id` 生成函数。
- 为 `ControlState` 增加 settlement map 和 append order。
- 在 `project_events` 中支持 `trajectory_settled`，验证 source work 已终止并保证同 ID 内容一致。
- 保持旧 event 和 legacy attempt-name migration 可读取。

### 4.2 修改 deterministic transitions

文件：`search_harness/evolution/control/transitions.py`

计划修改：

- 为 `TransitionPlan` 增加 `settlements`。
- `initial_work` 写入 optimizer episode 和第一个 research attempt ID。
- `retry_work` 保留 logical work ID。
- 新 generation 生成新的 generation-local research attempt ID，但保留 optimizer episode ID。
- 新 research attempt 生成新的稳定 `research_attempt_id`。
- 为 20 类既有 terminal branch 分配稳定 typed terminal code。
- Candidate promotion 在 Run 继续或完成时都生成 `settled_positive`。
- Candidate rejection 在定向 revision 或新 research attempt 继续时也生成 Candidate-level `settled_negative`。
- not-distillable 和 path-local budget terminal 生成 research-level `settled_negative`。
- work failure 生成 `invalid_indeterminate`，但不改变原 retry/resume route。
- 保留人类可读 `complete_reason`。

### 4.3 接入 Controller journal

文件：`search_harness/evolution/control/controller.py`

计划修改：

- 调用 `transition_completed` 时传入当前 `run_id`，保证 legacy work 也能获得稳定 episode lineage。
- completed work 产生 settlement 时，补充实际 `result_ref` 后追加 `trajectory_settled`。
- failed work 在 retry/pause 前追加 attempt-level `invalid_indeterminate` settlement。
- 保证 settlement event 在 `work_transitioned` 前写入。
- recovery 检测到已持久化 effect 时复用原 work 和 result，不产生重复 settlement。
- 不改变 stop-before、retry 次数、pause/resume 或 effect 执行顺序。

### 4.4 更新导出与架构说明

候选文件：

- `search_harness/evolution/control/__init__.py`
- `docs/architecture/evolution.md`

计划修改：

- 只在项目现有公共导出确有需要时导出 lineage/settlement 类型。
- 文档说明 episode、generation、research attempt、Candidate Attempt 和 work attempt 的包含关系。
- 文档说明 settlement event 与 Candidate Attempt journal 的职责区别。
- 文档明确这些合同是 H3 的输入基础，不等于 H3 experience system 已完成。

### 4.5 新增 TASK-005 development check

文件：`cvpr_workspace/checks/check_stage_001_settled_trajectory.py`

计划覆盖：

- 同一 run 得到稳定 optimizer episode ID；
- generation/research attempt ID 的包含关系；
- retry 改变 `work_id` 但保留 `logical_work_id`；
- promotion 形成唯一正向 settlement；
- Candidate reject 在继续 research 时仍形成 Candidate-level 负向 settlement；
- not-distillable 和预算 terminal 形成唯一负向 settlement；
- failed work 形成 invalid/indeterminate，而不是科研负结果；
- journal replay 不重复 settlement；
- 相同 settlement ID、不同内容触发错误；
- legacy event/work payload 仍可 replay。

检查输出计划保存到：

`cvpr_workspace/analysis/stage_001_settled_trajectory_check.json`

### 4.6 更新 TASK-004 inventory regression

文件：

- `cvpr_workspace/checks/check_stage_001_route_inventory.py`
- `cvpr_workspace/analysis/stage_001_route_coverage_matrix.json`

计划修改：

- 保留 TASK-004 的 63 条路由语义基线。
- 将旧的自然语言 `complete_reason` 数量护栏调整为 typed terminal code/settlement 覆盖护栏。
- 确保 20 个既有 terminal 语义没有因重构丢失或合并。

### 4.7 增加和运行回归测试

文件：`tests/evolution/test_control.py`

计划新增最小测试，覆盖：

- Controller journal 实际追加 settlement；
- retry/resume 不重复正负 settlement；
- Candidate rejection 与后续 research attempt 的双重边界；
- promotion 后新 generation lineage；
- interrupted effect recovery 的 settlement 幂等性。

计划运行：

1. TASK-005 专用 check；
2. TASK-004 route inventory regression；
3. `python -m unittest tests.evolution.test_control -v`；
4. `.cvpr` state validator；
5. `cvpr-do --mode preflight`；
6. TASK-005 完成后执行与阶段风险相称的 stage validator。

### 4.8 更新执行状态和证据

文件：

- `.cvpr/tasks.jsonl`
- `.cvpr/runs.jsonl`
- `.cvpr/state.yaml`
- `cvpr_workspace/入口清单.yaml`

计划修改：

- 登记 TASK-005 check 入口和手动命令；
- 追加所有成功、失败和中断 Run；
- 只有全部 acceptance criteria 有证据时才把 TASK-005 标记为 `accepted`；
- TASK-005 通过不等于 STAGE-001 通过，role identity contract 仍需后续原子任务完成。

本版本报告用于用户确认。除报告文件本身外，后续实际代码修改必须等待用户明确批准。

