# Intervention Worker 表达能力补强实验

## 目标

在不增加专用策略工具、不开放程序维护 metadata 的前提下，使 Intervention
Worker 能够实验最终 Hook Extension 已支持的阶段改写和跨阶段状态机制。本实验特别验证
关闭 thinking 的 Teacher Worker 是否能够稳定理解新增通用工具，不把工具面扩大转化为
错误动作或明显增加的重试。

## 可回退边界

新增能力由 `evolution.effects.intervention_extended_tools` 控制。设为 `false` 后，Worker
恢复原有 Context Patch、终答控制和无修改继续工具面；既有 artifact 和底层 Student
trajectory 格式不变。Intervention batch fingerprint 包含该开关，切换工具面不会复用旧
checkpoint。

## 实现假设

1. `inspect_active_stage` 按需返回当前 Phase 唯一可编辑的语义投影。
2. `apply_active_stage_patch` 只接收语义字段，由程序恢复内部对象并保留 metadata。
3. `update_trial_state` 写入有界、分支局部、JSON-compatible 状态；状态跨 Hook activation
   保留，每个 Trial Assignment 重置。
4. Scratch State 是 Intervention 试验语言；若机制获得支持，Distiller 仍需把它转成有
   类型、默认值、owner 和 writers 的正式 Hook State。

## 确定性验证

- `pre_tool` Stage Patch 已验证只改变待执行 Tool Call 参数，并保留工具身份与运行时对象。
- `post_tool → pre_final` 已验证 Scratch State 跨 Phase 可见，且不会进入 Student Model
  Input。
- 扩展工具默认关闭，正式配置显式启用；Intervention Worker thinking 显式设为
  `disabled`。

## 真实模型实验设计

固定使用 `20260815_qwen3-8b_hook_feasibility` 的 incumbent rollout
`5a7e36045542991319bc9440/r000`，不修改源 artifact。每个输入独立运行三次：

1. `pre_tool_query_patch`：把 live pending query 改成精确目标查询，验证结构化 Tool Call 编辑。
2. `post_model_action_rewrite`：把 live raw output 改成搜索 Tool Call，验证动作级重写。
3. `cross_phase_trial_state`：在 `post_tool` 写入显式状态，在 `pre_final` 基于状态决定是否
   退回终答，验证多阶段状态控制。

源边界初测、live 条件对照、live 强制改写与双角色联调分别保存于：

- `runs/experiments/20260816_extended_intervention_worker/`
- `runs/experiments/20260816_extended_intervention_worker_live/`
- `runs/experiments/20260816_extended_intervention_worker_live_v2/`
- `runs/experiments/20260816_researcher_intervention_joint/`

## 真实模型结果

### 1. 源边界初测发现实验语义错误

首轮 `pre_tool` 和 `post_model` 各运行三次，Worker 均提交了合法 Stage Patch；但进一步
核查发现，retained prefix 只能重建 Student-visible context，不能恢复原运行中尚未完成的
parser/tool transaction。源 `pre_tool` patch 虽被记录，却没有直接替换随后真正执行的调用；
源 `post_model` replacement 也只能作为重建上下文的一部分，而非同一笔解析事务。因此这
6 次只证明 Worker 会调用工具，不能证明阶段改写正确，未计入通过率。

据此做了两项修正：源边界不再提供不能忠实执行的 `post_model`、`post_parse`、`pre_tool`
Stage Patch；`fork_phase` 改为单独的恢复锚点，可早于首个 `phase_plan` 干预阶段。后者避免
为恢复 live transaction 强迫 Worker 处理一条 no-op phase。

### 2. 关闭 thinking 的 live Stage Patch

修正后固定输入各独立运行三次：

| 场景 | 忠实改写 | 实际执行目标动作 | Teacher 请求数 | 平均 token |
| --- | ---: | ---: | --- | ---: |
| live `pre_tool` Tool Call 参数 | 3/3 | 3/3 | 3、4、4 | 8,178 |
| live `post_model` raw action | 3/3 | 3/3 | 3、3、4 | 7,636 |

没有 API 错误、非法原生 tool call、Schema 错误或错误 stage 类型。多出来的一轮通常是
Worker 重复查看 context 目录或 active stage，不影响语义正确性。测试只证明设施能忠实
执行改写；分支最终答案仍可能错误，不能把工具成功等同于机制有效。

### 3. Trial state 的条件性

两批共六次 `post_tool → pre_final` 实验均正确保存
`missing_second_entity=true`。Student 在之后自然发起了第二实体检索，因此 Worker 六次
都在 `pre_final` 重新检查条件并选择 `continue_without_change`，没有因旧状态盲目 defer。
这证明 state 是历史观察而非强制动作开关。后一批三次平均 29,640 token，明显高于单阶段
改写，主要来自后续 phase 为判断“是否已经自然恢复”读取多个上下文块；因此 state 只应
用于真实跨 phase 依赖，不作为默认方案。

### 4. Researcher → Selector → Intervention 联调

使用同一冻结 Failure Direction 和 incumbent artifacts 独立运行三次。Researcher 产生
一次预防性 `post_tool` Context Patch 和两次纠正性 `pre_final` defer；正式 Trial Selector
均找到与 `fork_phase` 对应的 retained prefix，Worker 3/3 执行预期动作。

| 方案 | 次数 | Worker 直接效果 | 分支结果 |
| --- | ---: | --- | --- |
| `post_tool` 双边证据提示 | 1 | 下一动作搜索未查询实体 | 搜索发生，但最终答案仍错 |
| `pre_final` 一次性退回 | 2 | 下一动作搜索未查询实体 | 两次均由错误答案改为正确答案 |

Researcher 平均使用 73,305 token，Worker 平均 14,737 token。原 v4 长度上限使三次
Researcher 都因 `applicability` 为 305–331 字符重交一次；这些首稿在 v5 的 400 字符上限
下全部可直接通过，因而移除了纯格式性重试，而未改变产物语义。

## 结论与能力边界

- 关闭 thinking 的 Worker 能承担少量通用阶段工具：语义投影、单次原子改写、明确的
  branch-local state 更新和终答控制；本次未观察到工具面过大导致的动作混乱。
- `fork_phase` 必须与实际干预 phase 分离。它描述从哪里恢复，而 `phase_plan` 描述何时
  判断和行动；否则会产生不可忠实的源事务编辑或昂贵 no-op activation。
- Context Patch、Stage Patch 与 FinalDecision 都能稳定执行；Trial state 也可靠，但需要
  更多读取和语义判断，成本约为单阶段实验的 3–4 倍。
- 设施忠实性不保证 Student 效果。预防性方案已经补检索但仍答错，正是 Trial Reviewer
  和 Evidence Reviewer 必须继续判断行为效果与任务效果的原因。
- 本实验没有证明任一机制具备跨案例收益，也没有更改 Student Template、角色决策结果
  或源 artifacts。

## 对 Researcher Prompt 的影响

Researcher v5 现在明确：

1. 当前 Worker 支持 Context Patch、live Stage Patch、Trial-local state 与 pre-final control；
2. `fork_phase` 是恢复锚点，可早于首个真正干预 phase，不能为对齐字段增加 no-op 指令；
3. 选择“忠实表达因果方案的最低复杂度策略”，不能仅因 prompt patch 容易实现就把拆解、
   stage rewrite 或 stateful plan 降格成提示词；
4. Worker 关闭 thinking，phase instruction 应直接、有界，Trial state 仅在后续 phase 真正
   依赖早期观察时使用。
