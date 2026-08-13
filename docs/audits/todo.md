# Researcher—Intervention—Evidence 循环改造交接

## 目标

本轮改造聚焦于提高 Intervention 实验的有效覆盖和循环效率：

- Hypothesis Researcher 继续负责提出和修订可证伪假设。
- Controller 负责确定性选择、调度、计数和预算控制。
- Selector 以 `example_id` 为覆盖主轴，按小批次选择 Trial Assignment。
- 每批 Trial 完成后统一进入 Trial Review 和 Evidence Review，减少重复聚合审查。
- Hypothesis 修订后从零建立新版证据，旧 Trial 仅作为 Researcher 修订时的诊断材料。

## 一、Hypothesis 修订和证据重置

每次 Hypothesis Researcher 提交完整 Hypothesis 后，包括 revision 后的新版本，Controller 应初始化一个新的 Trial 循环：

- `trial_count = 0`
- `assignment_count = 0`
- `used_assignments = []`
- `prior_obligation = None`
- 清空尚未执行的批次和 assignment 队列。
- 新版 Evidence Review 只读取新版 Hypothesis 下重新执行产生的 Trial 和 Trial Review。

保留现有 `hypothesis_revision` 累计计数，以继续约束同一研究方向的总修订次数。

Researcher revision 执行期间仍应能够读取旧版 Trial。当前链路已经通过 `trial_files` 将旧 Trial 附加到 Researcher continuation；应保持这一能力。Researcher 提交新版 Hypothesis 后，旧 Trial refs 从后续 Controller payload 中移除，不进入新版 Coverage。

主要位置：

- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/control/effects.py`
- `search_harness/evolution/control/research_role_effects.py`
- `search_harness/evolution/research/roles/native_chat_runner.py`

## 二、强化 Evidence Reviewer 到 Researcher 的修订交接

更新 Evidence Reviewer Prompt。当 `decision == "revise"` 时，`assessment` 应提供足以直接指导 Researcher 修改完整 Hypothesis 的信息：

- 明确导致修订的决定性观察，包括必要的成功/失败比例、distinct coverage 和相关 Trial ref。
- 明确需要修改的 Hypothesis 部分及修改方向，例如 `applicability`、`activation_condition`、`instruction`、`expected_effect`、`success_condition` 或 `falsifier`。
- 明确已经得到支持、修订时应继续保留的机制、边界或过程效果。
- 明确新版 Hypothesis 不得继续声称的范围或收益。

Reviewer 应提供修订约束和证据结论，不直接编写替代 Intervention。

更新 Researcher Prompt 和 Evidence Reviewer continuation Prompt：

- 首先依据 Reviewer 的结构化反馈修订 Hypothesis。
- 当反馈已经足够时直接提交，不重复审判已确定的 Evidence。
- 只有在无法据此确定具体 condition、instruction 或 falsifier 时，才使用现有 Trial 工具读取证据。
- 读取顺序为 `list_trial_evidence` → `get_trial_evidence` → 必要时 `get_trial_event`。
- 优先检查 Reviewer 指出的决定性成功案例、反例或异常案例，避免无目的展开全部轨迹。
- 从案例中抽象通用条件，禁止把案例答案、实体或专属 query 写入新版 Hypothesis。

主要位置：

- `harness_templates/teacher/evidence_reviewer/prompt/system.md`
- `harness_templates/teacher/hypothesis_researcher/prompt/system.md`
- `harness_templates/teacher/hypothesis_researcher/prompt/continuations/evidence_reviewer.md`

## 三、Selector 改为分层批次取样

### Assignment 身份

Selector 应分别处理 Assignment 的三个层次：

- `example_id`：问题标识，是 distinct coverage 的计数单位。
- `replicate_id`：同一问题的独立 rollout，用于观察同一问题上的稳定性。
- `prefix_id`：同一 rollout 中的 Hook 边界，用于确定 Intervention 起点，不构成独立案例或独立 replicate。

Assignment key 继续使用：

```text
example_id/replicate_id/prefix_id
```

### 批次配置

在 Evolution Controller 配置中增加：

```yaml
trial_batch_size: 3
```

`trial_batch_size` 必须为正整数，且不得大于 `max_trials_per_hypothesis`。每次实际选择数量为：

```text
min(trial_batch_size, remaining_trial_budget, remaining_assignment_budget)
```

需要同步更新配置字段白名单、加载校验、`EvolutionControlConfig` 和默认 runtime 配置。

主要位置：

- `config/runtime.yaml`
- `search_harness/_internal/runtime_config.py`
- `search_harness/evolution/control/domain.py`

### 候选顺序

保留当前候选来源顺序：

1. Failure Analyst 的 `evidence_refs`。
2. 冻结 rollout 文件中的其他记录。

在候选来源内部，将选择顺序改为：

```text
example-first → replicate-second → phase-compatible prefix
```

所有排序必须来自冻结输入中的稳定顺序；相同状态必须产生相同批次。

### Fresh batch

只要存在当前 Hypothesis 版本尚未选择过的 `example_id`，批次应优先横向覆盖不同问题：

```text
X1/Y0/P
X2/Y0/P
X3/Y0/P
```

选择规则：

- 同一批次内 `example_id` 唯一。
- 每个新 example 只选择一个 replicate。
- 在该 replicate 中选择第一个 `phase == hypothesis.fork_phase` 且 assignment key 尚未使用的 prefix。
- 不因同一 example 存在多个 replicate 或 prefix 而连续占满批次。

### Replicate batch

当 fresh example 不足时，从已经选择过的不同 example 中，各选择一个尚未使用的 replicate：

```text
X1/Y1/P
X2/Y1/P
X3/Y1/P
```

选择规则：

- 优先将重复分散到多个 `example_id`。
- 同一个 `example_id` 在同一批次中最多增加一个 replicate。
- 新 replicate 同样选择第一个 phase-compatible、未使用的 prefix。
- same-example replicate 继续只用于稳定性观察，不增加 distinct example coverage。

如果 fresh example 和新 replicate 均不足，可继续选择剩余未用的 phase-compatible assignment；它仍按原 `example_id` 计数。

### Selector 输出

`select_trial()` 改为返回一个 assignment 列表，并持久化完整选择结果。建议内部结果形状：

```json
{
  "status": "selected",
  "selection_mode": "fresh",
  "assignments": [],
  "assignment_count": 3,
  "used_assignments": []
}
```

字段职责：

- `status`：说明本次是否选到候选或候选已经耗尽。
- `selection_mode`：记录本批主要是 fresh coverage 还是 replicate coverage，供审计使用。
- `assignments`：按确定性顺序排列的待执行 Assignment。
- `assignment_count`：当前 Hypothesis 版本累计选择的 Assignment 数量。
- `used_assignments`：当前 Hypothesis 版本已经选择过的完整 Assignment key。

主要位置：

- `search_harness/evolution/control/intervention_effects.py`
- `tests/evolution/test_intervention_effects.py`

## 四、批次执行和 Review 节奏

批次选择后可继续顺序执行 Assignment，不要求引入并行执行。Controller payload 保存待执行队列：

```text
pending_assignments
batch_assignment_count
batch_executed_count
```

字段职责：

- `pending_assignments`：当前批次尚未执行的 Assignment，按 Selector 返回顺序消费。
- `batch_assignment_count`：当前批次最初选入的 Assignment 数量，用于审计和恢复。
- `batch_executed_count`：当前批次已经成功形成 Trial 的数量，用于决定批次结束时是否进入 Evidence Review。

控制流程：

```text
SELECT_TRIAL
  → 保存 assignments 到 pending_assignments
  → EXECUTE_TRIAL

EXECUTE_TRIAL
  → executed：增加 trial_count 并保存 trial_NNN ref
  → unsuitable_assignment：不增加 trial_count
  → pending_assignments 非空：执行下一条
  → pending_assignments 为空且本批有 Trial：REVIEW_EVIDENCE
  → pending_assignments 为空且本批无 Trial：在预算允许时重新 SELECT_TRIAL
```

批次结束后：

- Trial Reviewer 仍独立审查每条新增 Trial。
- `EvidenceReviewEffects` 继续复用当前 Hypothesis 下已经存在且匹配的 Trial Review artifact。
- Evidence Reviewer 接收当前 Hypothesis 版本累计的全部 Trial Reviews 和 Coverage。
- 每个批次只调用一次 Evidence Reviewer。
- 进入 Evidence Review 前清理批次临时字段。

预算规则：

- Assignment 在被 Selector 选入批次时增加 `assignment_count` 并写入 `used_assignments`。
- Worker 返回 `executed` 时才增加 `trial_count`。
- `unsuitable_assignment` 消耗 assignment budget，但不增加 Trial 数。
- 批次选择不得超过剩余 Trial budget 或 Assignment budget。
- 候选或预算耗尽时沿用现有安全终止行为。

主要位置：

- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/control/effects.py`
- `search_harness/evolution/control/evidence_review_effects.py`
- `tests/evolution/test_control.py`

## 五、测试要求

### Selector 单元测试

- 第一批优先选择不同 `example_id`。
- Failure Analyst refs 仍优先于其他 rollout。
- 所有 prefix 与 `hypothesis.fork_phase` 匹配。
- 精确的 `example/replicate/prefix` 不会重复选择。
- fresh example 不足时，重复选择分散到多个既有 example 的新 replicate。
- 同一个 example 在一个 replicate batch 中最多出现一次。
- 同一 replicate 的其他 prefix 不会被当成新 replicate。
- 批次大小受配置和剩余预算共同限制。
- 候选耗尽时返回 `exhausted`。
- 相同冻结输入和状态产生相同批次及顺序。

### Controller 转移测试

- Selector 返回批次后按顺序消费全部 `pending_assignments`。
- pending 队列未清空时不会提前进入 Evidence Review。
- executed Trial 正确增加 `trial_count` 和 `trial_NNN` ref。
- unsuitable assignment 不增加 Trial 数，并继续批次中的下一条。
- 一批完成后只创建一个 `REVIEW_EVIDENCE` WorkItem。
- 整批无有效 Trial 时不会调用空 Evidence Review。
- Evidence Reviewer `continue` 后创建下一批。
- Hypothesis revision 清除批次状态、Trial refs、计数和 Coverage refs。
- Researcher revision 期间仍能通过现有工具访问旧 Trial。
- 新 Hypothesis 的 Evidence Review 不接收旧 Trial。

### Prompt 测试

- Evidence Reviewer 的 `revise` 指令要求提供决定性观察、修改方向、保留内容和 claim limit。
- Researcher revision 指令要求优先使用 Reviewer feedback，并按需读取 Trial。
- Researcher 的职责仍限定为假设形成和修订。

## 六、实施顺序

1. 更新三个角色 Prompt，并补充 Prompt 相关测试。
2. 增加 `trial_batch_size` 配置及加载校验。
3. 将 `select_trial()` 改为 example-first 的批次选择。
4. 在 Controller payload 中增加 pending batch 状态并调整转移逻辑。
5. 补充 Selector、预算、批次执行、revision reset 和 resume 测试。
6. 运行相关 Evolution 单元测试和一次最小 smoke run，确认 Evidence Reviewer 调用次数按批次而不是按 Trial 增长。

## 七、验收标准

- 初始批次在候选充足时覆盖 `trial_batch_size` 个不同 `example_id`。
- same-example replicate 不再优先于尚未选择的 example。
- 批次中的 Trial 全部处理完后才调用 Evidence Reviewer。
- Evidence Reviewer 调用次数与批次数一致，而不是与 Trial 数一致。
- Hypothesis revision 后新版 Evidence 从零累计，旧 Trial 只在修订阶段可读。
- Reviewer 的 `revise` 输出能够直接指导 Researcher 修改具体 Hypothesis 字段。
- Selector 和 Controller 在相同输入、配置和状态下保持可复现。
