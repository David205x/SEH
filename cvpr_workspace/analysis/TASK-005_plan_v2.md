# TASK-005 Plan v2

## 1. 当前状态

- TASK-005 已创建并启动，当前状态为 `running`，尚未验收。
- TASK-004 已完成 Controller 路由和终态语义审计，确认 H3 所需的 lineage 与 settled outcome 目前只能从多个事件、payload 和 artifact 中拼接。
- 在“代码修改前先汇报并等待批准”的要求提出前，`domain.py` 与 `transitions.py` 已产生未完成的中间修改。
- 中间修改新增了 `optimizer_episode_id`、哈希派生的 `research_attempt_id` 与 `settlement_id`；其中 `optimizer_episode_id` 与已有 `run_id` 重复，哈希 ID 也不符合本次修订后的实现要求。
- 中间修改把 `provisional` 放入 settlement 分类，但 provisional 结果并未形成可跨代消费的耐久结论，需从 settlement 合同中移出。
- Controller 尚未写入 settlement 事件，后续消费接口、失败路径、恢复路径和 replay 接线均未完成。
- 修改后的核心代码尚未执行 TASK-005 专用检查或控制链回归，当前中间态不能作为可用实现。
- 本报告取代 `TASK-005_plan_v1.md` 作为后续实施依据；在用户明确批准前，不继续修改研究核心代码。

## 2. 任务意图

TASK-005 要为 Controller 建立一条可直接读取的轨迹身份链，并在 Candidate、research attempt 或 work attempt 到达耐久边界时写入 typed settlement。这样，后续 H3 经验系统可以明确回答：结果属于哪一次 Run、哪一代、哪次研究尝试和哪次 Candidate 尝试；结果是否已经结算；结论来自哪个事件、work、verdict 和 artifact。

当前需要解决的问题是：

- `run_id` 已经能够唯一定位 Controller Run，不应再增加同义的 `optimizer_episode_id`。
- `generation` 当前只是 Run 内的正整数序号，缺少可被其他 artifact 直接引用的 `generation_id`。
- `research_attempt` 只有序号；Candidate rejection 后启动的新研究尝试需要稳定的 `research_attempt_id`。
- `candidate_attempt_id` 已由 Candidate Attempt journal 管理，但缺少到 Run、generation 和 research attempt 的显式反向定位。
- 正向结果、科研性负向结果和执行无效结果分散在 `complete_reason`、effect outcome、Candidate Attempt journal 与 failure event 中，后续消费者无法只依赖 typed contract 读取。
- retry 会更换实际执行 work；需要同时表达逻辑 work 和物理 work attempt，避免重复结算。

### H3 原文

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

TASK-005 实现这条主张的输入合同：稳定 lineage、typed terminal、settlement scope、outcome source 和 replay 投影。经验生成、Store、consumer projection 与失效机制由后续任务消费该合同实现。

## 3. 实施思路

### 3.1 Lineage 以 `run_id` 为根

计划采用以下包含关系：

```text
run_id
└── generation_id
    └── research_attempt_id
        ├── candidate_attempt_id（Candidate 物化后存在）
        └── logical_work_id
            └── work_id（一次物理执行，retry 时变化）
```

- `run_id` 直接表示一次 Controller Run，也是一次 optimizer episode；删除新增的 `optimizer_episode_id`。
- `generation` 保留为 Run 内从 1 开始的代次序号，用于预算、排序和用户输出。
- `generation_id` 是 `(run_id, generation)` 的可读组合身份。Run 初始化时创建第一代；Candidate promotion 产生新 version 且预算允许继续时，generation 加一并进入新的 `generation_id`。因此一次 Run 可以包含多个 generation，每个 generation 对应“以一个 accepted version 为 incumbent，持续研究直到产生下一次 promotion 或 Run 终止”的搜索区间。
- 同一 generation 内可以有多次 `research_attempt_id`。Candidate 被拒绝后重新进入问题分析时开启新的 research attempt；局部 evidence、mechanism 或 compiler revision 仍属于原 research attempt。
- `candidate_attempt_id` 继续由 Candidate Attempt journal 创建。创建 Candidate Attempt 时把 `run_id`、`generation_id` 和 `research_attempt_id` 写入 metadata，使 Candidate journal 可反向定位完整 lineage。

### 3.2 区分逻辑 work 与物理执行

- `logical_work_id` 标识一次应完成的控制工作，在 retry 期间保持不变。
- `work_id` 标识该逻辑工作的某一次实际执行，retry 时随 attempt 序号变化。
- settlement 的科研性正负结论绑定 `logical_work_id`；执行失败或中断绑定实际 `work_id`。
- `parent_work_id` 继续表达调度来源，用于重建控制路径，不承担跨 retry 去重职责。

### 3.3 Settlement 的定义

Settlement 是“某个明确 scope 已到达耐久边界”的 append-only 记录，不是 effect 的副本，也不是经验正文。它用于把分散的终态事实规范化为后续消费者可直接读取的合同。

每条 settlement 明确保存：

- `settlement_id`；
- `settlement_scope` 与 `scope_id`；
- `classification`：`settled_positive`、`settled_negative` 或 `invalid_indeterminate`；
- `terminal_code` 与 typed verdict；
- 完整 lineage；
- source Control event sequence、`work_id`、`logical_work_id`、result/artifact refs 和错误信息；
- 仍需处理时的 revision owner 与 obligation。

`provisional` 不属于 settlement classification。尚在 continuation 或 revision 中的结果继续保存在 work/effect 轨迹中；后续经验任务可以从这些轨迹生成 provisional summary，但不能把它当作 settled fact 跨 generation 使用。

`settlement_scope` 解决“局部结束但上层仍继续”的情况：Candidate rejection 可以结算该 `candidate_attempt_id`，同时原 generation 继续新的 research attempt；research budget 耗尽可以结算该 `research_attempt_id`；work failure 只结算该物理 `work_id` 为 `invalid_indeterminate`。

### 3.4 Settlement 的后续消费

消费链按以下职责分离：

1. Controller 在 source work 已持久化为 `completed` 或 `failed` 后追加 `trajectory_settled`，并由 journal replay 重建 settlement 投影。
2. STAGE-002 的 experience summarizer 按 `settlement_scope`、`classification`、typed verdict 和 source refs 选择输入，不解析 `complete_reason`。
3. 方向地图消费 research/Candidate scope 的 settled positive 与 settled negative；`invalid_indeterminate` 不形成科研性方向结论，只进入重试、复查或证据审计。
4. Student capability boundary 只消费与 feasibility/conformance 直接相关、且 scope 与 provenance 满足合同的 settlement。
5. Teacher role work experience 通过 source work kind、role identity 和 revision obligation 绑定到对应角色。
6. 生成的 experience 保存 `settlement_id` 作为 provenance；后续 invalidation、supersession 和 recheck 追加新记录，不覆写 settlement。

### 3.5 ID 设计

本任务涉及的 ID 使用可读组合或现有 journal 分配值，不使用哈希生成，也不通过比较哈希值验证身份。

已有并继续使用：

- `run_id`：Controller Run 的根身份，由运行入口提供。
- `candidate_attempt_id`：Candidate Attempt journal 分配的身份；本任务只补充 lineage metadata。
- `version_id`：accepted Harness version 的顺序身份，例如 `harness_v0002`。
- `parent_work_id`：实际调度父 work 的引用。
- Control event `sequence`：Run journal 内的追加顺序；source provenance 使用 `(run_id, sequence)`，不再额外生成 event ID。

本任务新增或规范化：

- `generation_id`：`{run_id}_generation_{generation:04d}`。
- `research_attempt_id`：`{generation_id}_research_{research_attempt:04d}`。
- `logical_work_id`：`{research_attempt_id}_work_{work_index:04d}_{work_kind}`。
- `work_id`：`{logical_work_id}_attempt_{attempt:02d}`。
- `problem_direction_id`：在 generation 内按首次创建顺序分配，例如 `{generation_id}_direction_{direction_index:04d}`；同一问题方向跨 research attempt 继续时沿用。
- `settlement_id`：`{scope_id}_settlement_{terminal_code}`；同一 scope 和 terminal 只能有一条耐久记录。

需要删除或收敛：

- 删除 `optimizer_episode_id`，统一使用 `run_id`。
- 删除哈希派生的 `_derived_id()` 及其 lineage/settlement 调用。
- 将现有哈希派生的 work 和 problem-direction 新建逻辑迁移为上述可读编号；历史 journal 中已有的旧 ID 作为普通字符串继续 replay，不重写。
- 删除与 `candidate_attempt_id` 同义的 `solution_attempt_id`；需要回指上一 Candidate 时使用 `prior_candidate_attempt_id`。
- `result_ref`、artifact ref、digest 和 Git commit 是内容或证据定位，不作为 lineage ID，也不参与 settlement 身份生成。

### 3.6 幂等与冲突处理

- 幂等依赖明确的 scope identity、terminal code、journal append 顺序和已存在记录检查，不依赖内容哈希。
- 相同 `settlement_id` 再次出现且 typed 字段相同，视为重复 replay；字段不一致时报告 journal 冲突。
- 历史记录保持原 ID 原样读取；新记录只使用可读 ID 规则，不批量改写旧 journal。

## 4. 计划实现

### 4.1 修正任务合同与 Control domain

文件：

- `.cvpr/tasks.jsonl`
- `search_harness/evolution/control/domain.py`

计划修改：

- 追加 TASK-005 修订记录，把 lineage 根从 `optimizer_episode_id` 改为 `run_id`，并把 provisional 从 settlement acceptance 中移出。
- 将 `TrajectoryLineage` 改为 `run_id`、`generation`、`generation_id`、`research_attempt_id` 和可选 `candidate_attempt_id`。
- 为 settlement 增加 `settlement_scope`、`scope_id` 和 source event sequence。
- settlement classification 只保留 `settled_positive`、`settled_negative`、`invalid_indeterminate`。
- 删除本次中间修改加入的 `hashlib`、`json` ID 派生函数和 `optimizer_episode_id`。
- 保留 `ControlState` 的 settlement map/order，并按 typed 字段执行 replay 冲突检查。
- 旧 journal 缺少新字段时只在读取边界按旧字段构造兼容投影，不覆写历史文件。

### 4.2 规范化调度 ID 与 generation 创建

文件：

- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/control/controller.py`

计划修改：

- Run 初始化时创建 `generation=1` 和对应 `generation_id`。
- Candidate promotion 后若 Run 继续，递增 generation 并创建新的 `generation_id` 和首个 `research_attempt_id`。
- Candidate rejection 后需要重新分析时，在原 generation 内递增 research attempt 序号并创建新的 `research_attempt_id`。
- 由 Controller 调度上下文分配 `work_index`，生成可读的 `logical_work_id` 与 `work_id`；retry 只递增物理 attempt。
- 删除 `_stable_id()`、`_lineage_id()` 以及新增的哈希 lineage helpers。
- `problem_direction_id` 在 generation 内顺序分配；方向继续时沿用，方向更换时递增。
- 将 `solution_attempt_id`/`prior_solution_attempt_id` 收敛为 `candidate_attempt_id`/`prior_candidate_attempt_id`。

### 4.3 接入 typed settlement 事件

文件：

- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/control/controller.py`
- `search_harness/evolution/control/journal.py`

计划修改：

- transition 只返回需要结算的 scope、classification、terminal code、verdict 与 revision obligation。
- Controller 在 `work_completed` 或 `work_failed` 已持久化后，补入 source event sequence 和 result/artifact refs，再追加 `trajectory_settled`。
- Candidate promotion 写入 Candidate scope 的 `settled_positive`。
- Candidate rejection 写入 Candidate scope 的 `settled_negative`；若继续研究，随后调度新的 research attempt。
- not-distillable 或 research-local budget terminal 写入 Research Attempt scope 的 `settled_negative`。
- work failure、中断且无完整 effect 写入 Work Attempt scope 的 `invalid_indeterminate`。
- journal replay 按 `settlement_id` 去重并检查 typed 内容冲突。

### 4.4 绑定 Candidate Attempt lineage

文件：

- `search_harness/evolution/control/candidate_version_effects.py`
- `search_harness/evolution/versioning/journal.py`

计划修改：

- 创建 Candidate Attempt 时写入 `run_id`、`generation_id`、`research_attempt_id` 和 source `logical_work_id` metadata。
- Candidate accepted/rejected event 继续使用原 `candidate_attempt_id`，settlement 通过该 ID 连接 Candidate journal 与 Control journal。
- 保留历史 `iteration_id` 到 `candidate_attempt_id` 的读取迁移。

### 4.5 更新文档与导出

文件：

- `search_harness/evolution/control/__init__.py`
- `docs/architecture/evolution.md`

计划修改：

- 仅导出 Controller、后续 summarizer 或检查代码实际需要的 lineage/settlement 类型。
- 文档写明 Run、generation、research attempt、Candidate attempt、logical work 和 physical work 的包含关系。
- 文档写明 settlement 的创建边界及 STAGE-002/003 消费职责。

### 4.6 建立 TASK-005 检查与回归

文件：

- `cvpr_workspace/checks/check_stage_001_settled_trajectory.py`
- `cvpr_workspace/checks/check_stage_001_route_inventory.py`
- `cvpr_workspace/analysis/stage_001_route_coverage_matrix.json`
- `tests/evolution/test_control.py`

计划验证：

- 一个 `run_id` 下 generation 递增时 `generation_id` 唯一且可读。
- 同 generation 的 research attempt 递增，Candidate rejection 与后续 research attempt 边界正确。
- retry 保留 `logical_work_id` 并产生新的 `work_id`。
- promotion、Candidate rejection、research terminal 和 work failure 分别落到正确 scope/classification。
- settlement replay 幂等，冲突内容被拒绝，且不使用哈希比较。
- Candidate Attempt metadata 能反向定位完整 lineage。
- legacy journal 仍能 replay，新 journal 不再生成哈希 lineage/work/settlement ID。
- route inventory 以 typed terminal 与 settlement scope 覆盖为护栏。

检查输出保存到 `cvpr_workspace/analysis/stage_001_settled_trajectory_check.json`，并按执行工作区契约登记入口和 Run 证据。

### 4.7 更新执行状态

文件：

- `.cvpr/tasks.jsonl`
- `.cvpr/runs.jsonl`
- `.cvpr/state.yaml`
- `cvpr_workspace/入口清单.yaml`

计划修改：

- 登记 TASK-005 check 入口和实际运行证据。
- 只有 lineage、settlement 创建、后续消费接口、retry/recovery/replay 和 legacy 兼容均有检查证据时，才将 TASK-005 标记为 `accepted`。

## 5. 盘点结果

### 5.1 当前 lineage 事实

- `ControlState.run_id` 由 `run_started` 事件重放得到；CLI 当前直接提供 `run_id`。证据：`search_harness/evolution/control/controller.py`、`search_harness/evolution/control/domain.py`、`search_harness/evolution/control/cli.py`。这支持直接使用 `run_id` 作为 lineage 根，不需要 `optimizer_episode_id`。
- `generation` 在 Run 初始化时为 1，只在 `version_advanced` 后更新；promotion 在预算允许时创建下一代 work。证据：`search_harness/evolution/control/domain.py`、`search_harness/evolution/control/transitions.py`。这支持把 generation 定义为 Run 内的 version-advancement 搜索区间，并补充 `(run_id, generation)` 对应的 `generation_id`。
- Candidate rejection 可以在同一 generation 内开启新的 research attempt；局部 revision 不开启新 attempt。证据：`search_harness/evolution/control/transitions.py`。这支持 generation 下包含多个 research attempt 的层级。
- Candidate Attempt journal 已独立生成并持久化 `candidate_attempt_id`，accepted version 也保存该引用。证据：`search_harness/evolution/versioning/journal.py`、`search_harness/evolution/versioning/store.py`。因此本任务只需补 lineage metadata 和跨 journal 连接，不需新建第二套 Candidate ID。

### 5.2 当前 ID 与哈希事实

- 现有 transition 使用 `_stable_id()` 的 SHA-256 截断值生成 `work_id`，`problem_direction_id` 也由 `_lineage_id()` 的 SHA-256 截断值生成。证据：`search_harness/evolution/control/transitions.py`。
- TASK-005 中间修改又在 `domain.py` 增加 `_derived_id()`，用于 `optimizer_episode_id`、`research_attempt_id` 和 `settlement_id`。证据：`search_harness/evolution/control/domain.py`。
- 这些哈希只把已知结构字段压缩成不透明字符串，没有承担内容完整性验证；journal 自身已有顺序、typed 字段和冲突检查。因此新实现可以用可读组合 ID 与字段比较完成身份和 replay 核对。
- artifact digest、Candidate content digest 和 Git commit 属于内容/版本证据，不是 TASK-005 lineage ID；本任务不改动它们。

### 5.3 Settlement 消费缺口

- 当前 Controller 只持久化 work completion/failure、version advancement、run completion 和 effect artifact；尚无已接线的 settlement event。证据：`search_harness/evolution/control/controller.py`。
- 当前正负结果需要结合 `complete_reason`、effect outcome、Candidate Attempt event 和版本记录推断。证据：`search_harness/evolution/control/transitions.py`、`search_harness/evolution/control/candidate_version_effects.py`、`search_harness/evolution/versioning/journal.py`。
- PLAN-001 的 STAGE-002 要求 direction map、Student capability boundary 和 Teacher role work experience 消费有 provenance 的 settled outcome。TASK-005 必须先提供 typed scope、classification 与 source refs，后续任务才不需要重新解释自然语言终态。

### 5.4 当前验证限制

- TASK-005 中间修改后尚未运行专用检查或控制链回归，且 Controller 接线未完成。当前只能确认设计和缺口，不能确认实现可执行或 replay 一致。

本版本报告用于用户确认。除报告和项目级汇报规则外，后续代码及状态修改等待用户明确批准。
