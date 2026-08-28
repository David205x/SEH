# TASK-005 Plan v3（待确认）

## 1. 当前状态

- TASK-005 当前为 `running`，尚未验收，实施方案尚未获得用户确认。
- TASK-004 已确认 H3 所需 lineage 与 settled outcome 目前分散在 Control journal、work payload、effect artifact、Candidate Attempt journal 和 Version Store 中。
- `domain.py` 与 `transitions.py` 存在批准流程建立前留下的未完成中间修改；Controller 尚未接入 settlement 写入和消费链。
- 中间修改引入的 `optimizer_episode_id`、哈希 ID helper、`scope_id` 设想和 provisional settlement 均不进入本版方案。
- 当前运行时代码仍包含旧 ID 名称迁移、旧 schema 读取、旧文件名回退、哈希派生 work ID 和多个同义 ID。
- TASK-005 修改后的专用检查和控制链回归尚未执行，现有中间态不能视为可用实现。
- 本文件是未确认的 v3 讨论稿；用户确认前不修改核心代码、执行状态或任务账本。

## 2. 任务意图

TASK-005 要建立唯一、可读、typed 的 Controller 生命周期身份链，并在 Candidate Attempt、Research Attempt 或 Work Attempt 到达耐久边界时形成 settlement。后续 H3 组件应直接依据结构化字段定位结果、判断结算性质和读取 provenance，不再解析自然语言原因、旧字段别名或 ID 字符串内部片段。

本任务解决：

- 用 `run_id` 统一表示一次 Controller Run/optimizer episode。
- 为 Run 内的每一代建立 `generation_id`，区分多 generation 搜索区间。
- 为 generation 内的研究尝试、Candidate 尝试、逻辑 work 和物理执行建立明确包含关系。
- 把 Candidate 正负终态、Research terminal 和 Work failure 规范为 typed settlement。
- 统一所有相关 ID 的生成入口、格式、验证与消费方式。
- 删除旧 ID 名称、旧 schema、旧文件回退和哈希派生实现，只保留新合同。

### H3 原文

> 将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。

TASK-005 负责这条主张的输入合同：lineage、typed terminal、settlement scope、outcome source 和 journal replay 投影。后续任务据此生成和消费 experience。

## 3. 实施思路

### 3.1 Lineage 层级

```text
run_id
└── generation_id
    └── research_attempt_id
        ├── candidate_attempt_id（Candidate 物化后存在）
        └── logical_work_id
            └── work_id（一次物理执行）
```

- `run_id` 是 lineage 根，直接表示一次 Controller Run。
- `generation` 是 Run 内从 1 开始的序号；`generation_id` 是其可引用身份。
- Run 初始化时进入第一代。Candidate promotion 产生 accepted version 且继续搜索时，generation 加一并进入新的 `generation_id`。
- 一个 generation 表示“以同一个 accepted version 为 incumbent，持续研究直至下一次 promotion 或 Run 终止”的搜索区间，因此一次 Run 可以包含多个 generation。
- 同一 generation 内可以有多次 research attempt。Candidate rejection 后重新进入问题分析时开启新的 `research_attempt_id`；Evidence、Mechanism、Compiler 等局部 revision 仍属于当前 research attempt。
- Candidate 物化时创建 `candidate_attempt_id`，并在 Candidate journal metadata 中写入上层 lineage。

### 3.2 Logical Work 与 Work Attempt

- `logical_work_id` 表示一次逻辑控制工作，retry 时保持不变。
- `work_id` 表示一次物理执行，包含 attempt 序号，retry 时创建新值。
- `parent_work_id` 表示实际调度来源，只用于重建 work 路径。
- 科研性 settlement 通过 lineage 连接逻辑 work；执行失败 settlement 直接绑定发生失败的 `work_id`。

### 3.3 Settlement 合同

Settlement 是某个生命周期对象到达耐久边界后的 append-only typed 记录。它不复制 effect 内容，也不保存经验正文。

每条 settlement 保存：

- `settlement_id`：settlement 记录的稳定引用和幂等键；
- `settlement_scope`：`candidate_attempt`、`research_attempt` 或 `work_attempt`；
- `classification`：`settled_positive`、`settled_negative` 或 `invalid_indeterminate`；
- `terminal_code` 与 typed verdict；
- `TrajectoryLineage`；
- source Control event sequence、`work_id`、`logical_work_id`、result/artifact refs 和错误信息；
- 适用时的 revision owner 与 revision obligation。

不保存 `scope_id`。它会重复 lineage/source 中已经存在的身份，并产生双重事实源。scope 对应的目标按类型直接取得：

- `candidate_attempt` → `lineage.candidate_attempt_id`，该字段必须存在；
- `research_attempt` → `lineage.research_attempt_id`；
- `work_attempt` → `source.work_id`。

`settlement_id` 的生成函数内部使用上述目标 ID 与 `terminal_code` 形成可读键，但消费者不得解析 `settlement_id`。消费者读取 `settlement_scope`，再从对应 typed 字段取得目标身份。

尚在 continuation 或 revision 中的结果不创建 settlement。后续任务可以根据未结算轨迹生成 provisional summary，但 provisional 不是 settlement classification，也不能作为跨 generation settled fact。

### 3.4 Settlement 创建边界

- Candidate promotion：为该 `candidate_attempt_id` 写入 `settled_positive`。
- Candidate rejection：为该 `candidate_attempt_id` 写入 `settled_negative`；需要继续研究时随后创建新的 research attempt。
- not-distillable、research-local revision/budget terminal：为当前 `research_attempt_id` 写入 `settled_negative`。
- Work failure 或无完整 effect 的中断：为实际 `work_id` 写入 `invalid_indeterminate`。
- generation 作为聚合层，不单独创建 settlement；其结果由该 generation 下的 Candidate/Research settlements 与 version advancement 共同表达。

### 3.5 Settlement 消费

1. Controller 在 source work terminal event 已持久化后追加 `trajectory_settled`，Control journal replay 重建 settlement projection。
2. STAGE-002 summarizer 根据 `settlement_scope`、classification、typed verdict 与 source refs 选择输入，不解析 `settlement_id` 或 `complete_reason`。
3. Direction map 使用 Candidate/Research scope 的 settled positive 和 settled negative，并通过 lineage 聚合到 generation 与 problem direction。
4. Student capability boundary 使用与 feasibility/conformance 直接相关的 settlement。
5. Teacher role work experience 使用 source work kind、role identity 和 revision obligation 定位角色经验。
6. `invalid_indeterminate` 只进入重试、复查和证据审计，不生成科研性正负经验。
7. Experience provenance 引用 `settlement_id`；失效、替代和复查记录引用该 ID，但仍从 settlement typed 字段读取事实。

### 3.6 统一 ID 规则

所有生命周期 ID 由共享的 ID 模块生成和校验。ID 采用安全字符、明确前缀和可读序号，不使用内容哈希或哈希比较。

- `run_id`：`run_<UTC timestamp>_<random suffix>`，由运行入口通过共享生成器创建。
- `generation_id`：`<run_id>_g<generation:04d>`。
- `research_attempt_id`：`<generation_id>_r<research_attempt:04d>`。
- `candidate_attempt_id`：`candidate_attempt_<UTC timestamp>_<random suffix>`，由 Candidate journal 通过共享生成器创建。
- `problem_direction_id`：`<generation_id>_d<direction_index:04d>`；同一方向跨 research attempt 继续时沿用。
- `logical_work_id`：`<research_attempt_id>_w<work_index:04d>_<work_kind>`。
- `work_id`：`<logical_work_id>_a<attempt:02d>`。
- `settlement_id`：Candidate scope 使用 `<candidate_attempt_id>_settlement_<terminal_code>`；Research scope 使用 `<research_attempt_id>_settlement_<terminal_code>`；Work scope 使用 `<work_id>_settlement_<terminal_code>`。
- `version_id`：继续使用 Version Store 的顺序身份 `harness_vNNNN`。
- Control event 不新增 event ID；provenance 使用 `(run_id, sequence)`。

共享生成器只接受明确的父 ID、序号和 enum 值。消费者使用完整字段等值匹配，不拆解字符串恢复 lineage；字符串格式只服务于可读性、路径安全和人工审计。

### 3.7 删除旧 ID 与兼容实现

新运行时只接受当前 schema 和当前字段：

- 删除 `optimizer_episode_id`，统一使用 `run_id`。
- 删除 `iteration_id` 到 `candidate_attempt_id` 的递归迁移。
- 删除 Candidate journal 的旧 `iterations.jsonl` 读取和 `legacy_path`。
- 删除 Version Store 对 `checkpoint.json`、`checkpoint_store_id` 和旧 Version Record schema 的回退。
- 删除 Control CLI 对旧 Run schema 和 `checkpoint_store` 字段的内存迁移。
- 删除 `solution_attempt_id`、`prior_solution_attempt_id`，统一使用 `candidate_attempt_id`、`prior_candidate_attempt_id`。
- 删除 `_stable_id()`、`_lineage_id()`、`_derived_id()` 及相应哈希 import。
- `logical_work_id`、lineage 字段和 settlement 字段在新 schema 中设为必填，不再以 `work_id`、payload 或 `subject_ref` 猜测缺失值。
- 删除旧兼容测试和 fixture；增加“旧 schema/旧字段被明确拒绝”的边界检查。
- 活跃架构文档和示例只描述新 ID；历史数据文件不由本任务改写，但新运行时不再加载它们。

### 3.8 幂等与一致性

- `settlement_id` 由 typed scope 目标和 terminal code 确定，不使用哈希。
- replay 遇到相同 `settlement_id` 和相同 typed 内容时保持单条投影；同 ID 内容不一致时拒绝 journal。
- retry 复用 `logical_work_id` 并递增 `work_id` attempt；科研性 terminal 只结算对应 Candidate/Research scope，失败 attempt 各自结算为 `invalid_indeterminate`。
- 新 schema 的 ID 必须由共享生成器或解析后的受控外部 `run_id` 产生，调度和 effect 代码不得自行拼接另一种格式。

## 4. 计划实现

### 4.1 建立共享 ID 模块

文件：`search_harness/evolution/identifiers.py`

计划实现：

- 定义 Run、generation、research attempt、Candidate attempt、problem direction、logical work、work attempt 和 settlement ID 的生成函数。
- 定义安全字符、前缀、正整数序号与长度验证。
- 定义按 `settlement_scope` 从 typed lineage/source 选择 settlement 目标 ID 的函数；不产生或保存 `scope_id`。
- 生成器不导入 `hashlib`，验证器不比较哈希值。

### 4.2 重建 Control domain 合同

文件：`search_harness/evolution/control/domain.py`

计划实现：

- `WorkItem` 明确保存 `logical_work_id`、`work_id`、`parent_work_id` 和 attempt；新 schema 不提供缺失字段回退。
- `TrajectoryLineage` 保存 `run_id`、`generation`、`generation_id`、`research_attempt_id` 和可选 `candidate_attempt_id`。
- settlement 保存 `settlement_scope`，不保存 `scope_id`。
- `OutcomeSource` 保存 source event sequence、work identities、result/artifact refs、verdict 与错误。
- `WorkRecord` 投影 terminal event sequence，供 settlement 绑定 source Control event。
- `ControlState` 投影当前 ID 分配序号、settlement map 和 append order。
- 删除中间实现的 optimizer episode、provisional settlement 和哈希 ID helper。

### 4.3 规范 Controller 调度与 ID 分配

文件：

- `search_harness/evolution/control/controller.py`
- `search_harness/evolution/control/transitions.py`

计划实现：

- Controller 初始化时保存 `run_id`、第一代 `generation_id`、首个 `research_attempt_id` 和 ID 分配序号。
- Controller 为 transition 返回的待调度 work 分配 `work_index`、`logical_work_id` 和首个 `work_id`。
- retry 沿用 `logical_work_id`，只增加 attempt 并生成新 `work_id`。
- promotion 后继续运行时创建下一 `generation_id` 和首个 research attempt。
- Candidate rejection 后继续研究时在当前 generation 创建下一 research attempt。
- problem direction 由 generation-local 序号分配，不再从 artifact/work 内容计算哈希。
- transition 使用 typed lineage，不从 payload、`subject_ref` 或旧别名推断 ID。
- 删除 `solution_attempt_id` 及旧哈希 helper 的生成和消费点。

### 4.4 接入 settlement journal

文件：

- `search_harness/evolution/control/controller.py`
- `search_harness/evolution/control/transitions.py`
- `search_harness/evolution/control/journal.py`

计划实现：

- transition 返回 settlement classification、scope、terminal code、verdict 和 revision obligation。
- Controller 使用 terminal WorkRecord 中的 source event sequence、result ref 与 error 构造完整 settlement。
- Controller 在 `work_transitioned` 前追加 `trajectory_settled`。
- replay 按 settlement ID 和 typed 内容验证唯一性。
- Control journal 与 effect reader 直接读取当前 schema，删除 attempt-name 迁移函数。

### 4.5 规范 Candidate Attempt 与 Version Store

文件：

- `search_harness/evolution/control/candidate_version_effects.py`
- `search_harness/evolution/versioning/journal.py`
- `search_harness/evolution/versioning/store.py`
- `search_harness/evolution/control/cli.py`

计划实现：

- Candidate Attempt 创建时保存 `run_id`、`generation_id`、`research_attempt_id` 和 source `logical_work_id` metadata。
- Candidate ID 与 Run ID 使用共享生成器。
- Candidate journal 只读取当前 `candidate_attempts.jsonl` schema。
- Version Store 只读取 `version_store.json`、当前 Version Record schema 和 `candidate_attempt_id`。
- Control CLI 只接受当前 Run schema 与 `version_store_id`。
- 旧字段或旧 schema 输入立即返回明确错误，不做内存迁移。

### 4.6 清理消费点、测试与文档

文件：

- `search_harness/evolution/control/__init__.py`
- `tests/evolution/test_control.py`
- `tests/evolution/test_control_cli.py`
- `tests/evolution/versioning/`
- `docs/architecture/evolution.md`

计划实现：

- 更新所有 WorkItem fixture、Candidate metadata、journal fixture 和断言为新 ID 合同。
- 删除 legacy attempt/store/run schema 兼容测试，增加旧输入被拒绝的检查。
- 检查生产代码、活动测试和活动架构文档中不再出现被删除的 ID 名称或 migration helper。
- 公共导出只保留实际消费者使用的 typed contract 和共享 ID API。

### 4.7 建立 TASK-005 检查

文件：

- `cvpr_workspace/checks/check_stage_001_settled_trajectory.py`
- `cvpr_workspace/checks/check_stage_001_route_inventory.py`
- `cvpr_workspace/analysis/stage_001_route_coverage_matrix.json`

计划验证：

- 所有新 ID 由共享模块生成，格式可读、路径安全且无哈希派生。
- Run 内多 generation、generation 内多 research attempt 的包含关系正确。
- Candidate metadata 可反向定位 Run、generation 和 research attempt。
- retry 保持 logical work，改变物理 work attempt。
- Candidate、Research 与 Work settlement 使用正确 scope，并从 typed 字段取得目标身份。
- 消费者不解析 `settlement_id`、`work_id` 或 `complete_reason` 推断语义。
- 旧 schema、旧字段、旧文件名和旧 ID alias 不再被运行时接受。
- promotion、rejection、research terminal、failure、resume 和 replay 的结算唯一性正确。
- route inventory 使用 typed terminal 与 settlement scope 作为覆盖护栏。

### 4.8 更新任务合同与执行证据

文件：

- `.cvpr/tasks.jsonl`
- `.cvpr/runs.jsonl`
- `.cvpr/state.yaml`
- `cvpr_workspace/入口清单.yaml`

计划实现：

- 方案获批后先追加 TASK-005 修订记录，移除 optimizer episode、provisional settlement 和 legacy compatibility 验收描述。
- 登记 TASK-005 check 入口与实际 Run 证据。
- 只有 ID 生成与消费统一、旧实现清理、settlement 接线、失败/恢复/replay 和边界检查均通过后，才将 TASK-005 标记为 `accepted`。

## 5. 盘点结果

### 5.1 `scope_id` 判断依据

- lineage 已保存 `candidate_attempt_id` 与 `research_attempt_id`，OutcomeSource 已保存 `work_id`。若 settlement 再保存 `scope_id`，同一身份会出现两个字段。证据：`search_harness/evolution/control/domain.py` 的中间 settlement/lineage/source 模型。
- 后续消费者需要的是 typed scope 与对应实体，而不是一个需要解释的通用字符串。删除 `scope_id` 后，`settlement_scope` 可以对相应 typed 字段施加强制存在约束。
- `settlement_id` 仍有独立职责：它是 settlement 记录本身的引用、去重键以及 experience/invalidation 的 provenance key；它不承担向消费者表达 scope 目标的职责。

### 5.2 当前 ID 生成与消费事实

- Run ID 当前由 Control CLI 直接生成 UUID 字符串，generation 只有整数序号。证据：`search_harness/evolution/control/cli.py`、`search_harness/evolution/control/domain.py`。
- work ID 与 problem direction ID 当前由 `transitions.py` 的 SHA-256 截断 helper 生成；TASK-005 中间修改又增加了 lineage/settlement 哈希 helper。证据：`search_harness/evolution/control/transitions.py`、`search_harness/evolution/control/domain.py`。
- Candidate Attempt ID 当前由 Candidate journal 生成时间戳加随机后缀，Version ID 由 Version Store 顺序分配。证据：`search_harness/evolution/versioning/journal.py`、`search_harness/evolution/versioning/store.py`。
- `solution_attempt_id` 当前只是 `candidate_attempt_id` 的同义复制，`prior_solution_attempt_id` 用于回指。证据：`search_harness/evolution/control/transitions.py`。这支持删除同义字段并统一 Candidate identity。
- work ID 同时用于 journal 引用、artifact 目录和 retry 路径；新格式必须满足单个 Windows 路径组件约束。证据：`search_harness/evolution/control/journal.py`、`search_harness/evolution/control/controller.py`。

### 5.3 当前兼容实现事实

- Control journal 与 effect reader 会递归把 `iteration_id`/`iteration_*` 迁移为 Candidate Attempt 名称。证据：`search_harness/evolution/control/journal.py`。
- Candidate Attempt journal 同时读取 `candidate_attempts.jsonl` 与旧 `iterations.jsonl`，并接受旧 schema。证据：`search_harness/evolution/versioning/journal.py`、`search_harness/evolution/versioning/store.py`。
- Version Store 会回退到 `checkpoint.json`、`checkpoint_store_id` 和旧 Version Record 字段。证据：`search_harness/evolution/versioning/store.py`。
- Control CLI 会把旧 Run schema 的 checkpoint store 字段迁移为 version store 字段。证据：`search_harness/evolution/control/cli.py`。
- 活动测试仍包含上述兼容行为的正向断言。证据：`tests/evolution/test_control.py`、`tests/evolution/test_control_cli.py`、`tests/evolution/versioning/`。

### 5.4 当前验证限制

- TASK-005 中间修改尚未完成 Controller 接线，也未运行修改后的专用检查或控制链回归。当前结论只支持方案修订和清理范围，不能支持实现已正确。

本方案当前未确认。后续核心代码、任务账本和执行状态修改等待用户明确批准。
