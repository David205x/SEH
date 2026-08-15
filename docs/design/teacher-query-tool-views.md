# Teacher 查询工具模型可见视图

状态：已确认的实施规格
当前实施阶段：正式主链路迁移与影子实现清理已完成
最后更新：2026-08-14

2026-08-14 收口：通过真实 API 验证的视图已迁入正式角色；影子模板、影子 Role
Factory、对应 A/B 执行入口和只验证影子实现的测试已从活动代码删除。本文前半部分保留的
`experiments/teacher_query_views/` 路径只描述历史实验环境，真实结果继续保存在
`runs/experiments/`，不表示当前仓库仍提供这些影子入口。

## 1. 目的与范围

本设计只优化 Teacher Model 通过查询工具读取的模型可见内容。底层 Artifact 继续尽量
保留完整事实、Provider metadata、原始 Tool Result、完整 Model Input 和 Harness
生命周期事件；模型可见视图是从 Artifact 派生的有损投影，不是新的事实源。

以下是迁移前影子代码曾覆盖的范围，保留用于解释后续 A/B 结论：

1. Teacher Judgment 输出 `score` 与简短 `assessment`；
2. `get_evaluation_case` 默认精简视图；
3. Student Trajectory 去重、Student 有效上下文与 Extension Change 分层视图；
4. Failure Analyst 使用的 Student Capability View；
5. Hypothesis Researcher 使用的 Student Behavior Interface。
6. Intervention Worker 使用的紧凑 Editable Context 与精确 Block View。

Intervention Worker 当时作为第二轮影子实验实现，没有直接改变正式 Worker 的默认查询
工具。Trial Reviewer 的影子实现随后放弃；Mechanism Distiller 的影子实现完成真实 API
A/B 后，其验证有效的视图已迁入正式模板。当前状态以第 16 节为准。

## 2. 实施与迁移约束

- 第一轮只建立影子角色、影子工具和独立实验脚本，不删除、不覆盖、不改名正式工具。
- 影子角色使用与正式角色相同的 Role Input、既有 Artifact 和 Model Configuration。
- 确定性视图先进行离线检查；角色行为随后使用真实 API 对同一输入默认重复三次。
- 影子结果没有满足本文验收标准前，不切换正式 Teacher Harness Template。
- 正式切换与旧工具删除是独立任务，需要基于 Focused Probe 结果再次确认。
- 影子实现不得修改 Student Template、Teacher Role 的研究机制或已有 Artifact 内容。

## 3. 模型可见内容排版

模型可见 Tool Output 不统一使用 JSON。各部分按信息形态选择最紧凑且边界清晰的
表达：

- 固定标量和两侧比较使用 Markdown 表格；
- 简短规则、结论和可用性说明使用密集短文本；
- 事件流使用紧凑 JSONL 或逐事件短块；
- 需要保持精确空白和结构的正文使用带明确边界的原始内容块；
- 程序接口之间继续使用结构化 Python 数据，排版只发生在 Tool Output 渲染层。

Summary 只用于导航。任何摘要、preview 或派生分类都必须明确标注，不能替代精确
Evidence。

## 4. Teacher Judgment 与 Evaluation Case

### 4.1 Teacher Judgment

Teacher Judgment 的正常语义输出为：

- `score`：Teacher 对当前 Evaluation Input 给出的评分值；
- `assessment`：一至两句、建议不超过约 240 字符的判分依据，不包含原始推理过程。

Provider usage、native reasoning、raw output、请求 metadata 和错误诊断继续完整保存在
Artifact。它们不进入 `get_evaluation_case` 默认 Tool Output。

### 4.2 `get_evaluation_case` 默认视图

默认视图固定呈现所有规定字段；没有对应事实时显式使用：

- `none`：该对象明确没有该值；
- `n/a`：该字段不适用于当前对象；
- `unavailable`：数据源没有提供该值；
- `unresolved`：Evaluation 尚未形成结论。

每个 Replicate 保留：

- `replicate_id`：当前独立 Student Rollout 的身份；
- `score`：当前 Replicate 的最终评分；
- `assessment`：Teacher Judgment 的简短判分依据；
- `predicted_answer`：Student Run 返回的 Answer；
- `run_status`：Student Run 的终态；
- `runner_error`：Runner 失败信息；
- `steps`：Student Run 实际 Lifecycle Step 数；
- `tool_calls`：Student 发起的 Tool Call 数；
- `retriever_errors`：Retriever 执行错误数；
- `duplicate_queries`：重复查询数；
- `input_tokens`：该 Replicate 的输入 token；
- `output_tokens`：该 Replicate 的输出 token；
- `total_tokens`：该 Replicate 的总 token；
- `student_total_tokens`：存在 Hook Model 用量时的 Student Model 总 token；
- `hook_total_tokens`：存在 Hook Model 用量时的 Hook Model 总 token。

不保留 `model_calls`。Case 聚合只保留选择与判断所需的稳定性、成功率、Replicate
数量和必要的执行摘要，不回显 Teacher raw output、reasoning 或 Provider metadata。

## 5. Student Trajectory View

### 5.1 事实边界

Trajectory View 使用三个固定可见性标签：

- `STUDENT_VISIBLE`：该内容存在于一次实际提交给 Student Model 的 Model Input；
- `RUNTIME_ONLY`：Tool 或 Extension 处理过该内容，但它没有进入相应 Student Model
  Input；
- `DERIVED_VIEW`：投影程序生成的目录、preview、change 分类或说明。

“已送入 Student”只能由最终记录的 Model Input 验证。仅有 `hook_applied` 或 Extension
声明不足以证明内容已经送达；无法验证时使用 `delivery_status=unverified`。

### 5.2 去重规则

角色投影统一删除：

- 与 `ToolResult.content` 重复的 `ToolResult.metadata.results`；
- 描述已经省略内容的固定 `omitted` 字段；
- 每一步累计重复的完整 Model Input；
- Provider usage、路径、Provenance 和任务无关 metadata。

底层 Artifact 不删除这些内容。

### 5.3 Context Revision 与 Block

每次 Student Model Call 对应一个 Context Revision。Revision 使用有序 Block Reference
表示精确输入顺序；默认只展开相对上一 Revision 新增或改变的 Block。

- `block_id`：一个上下文块的数字身份；
- `revision`：该逻辑块内容发生变化后的版本号；
- `role`：该块在 Model Input 中的 Message Role；
- `kind`：普通 Message、Tool Result 或其他受支持内容种类；
- `characters`：精确内容字符数；
- `content_state`：当前 Tool Output 提供 `complete` 还是 `preview`；
- `sent_to_student`：该精确 Block Revision 是否存在于目标 Model Input。

大块内容通过 Block Reference、offset 和最大字符数分段读取。精确读取不得使用会显著
增加转义的嵌套 JSON 字符串。

### 5.4 Extension Change

Change 由投影程序根据 Lifecycle Phase、State Change 和后续 Model Input 确定性构造：

- `change_id`：本条 Trajectory 内的变化身份；
- `hook_id`：产生变化的 Hook 身份；
- `phase`：Hook Invocation 所处 Lifecycle Phase；
- `effect_kind`：`insert`、`replace`、`delete`、`compress` 或可验证的其他结构变化；
- `target`：被修改的 Stage State 或上下文对象；
- `source_refs`：变化前的 Block Revision；
- `effective_refs`：变化后的 Block Revision；
- `delivery_status`：变化结果是否经 Model Input 验证送入 Student；
- `declared_purpose`：Extension 自己声明的目标，不能当作实际执行事实。

小范围、局部变化默认返回紧凑 diff。大段语义重写或压缩返回输入输出规模、压缩比例、
Block 映射、Student 有效内容 preview 和下钻引用，不生成另一份冒充证据的语义摘要。

Hook Invocation 与 Mechanism Activation 必须分开呈现。Hook 被调用但没有修改上下文时，
视图明确记录 `student_context_changed=no` 及可观察的 no-op/fallback 结果。

### 5.5 渐进读取接口

影子实现验证以下职责，而不在第一阶段替换正式工具名：

- Trajectory 默认查询：返回 Outcome、Context Revision、有效事件和紧凑 Change；
- Change 查询：返回一条 Change 的结构比较、局部 diff 和 Evidence Reference；
- Block 读取：按 Block ID、Revision、offset 和长度返回精确内容；
- Block 搜索：在大型 `RUNTIME_ONLY` 原文中确定性查找相关片段。

## 6. Failure Analyst Capability View

Failure Analyst 只诊断有 Evidence 支持的 Student 行为，不解释根因或提出实现方案。原始
`get_harness_manifest` 对该职责既包含过多装配信息，又缺少可观察行为信息。

影子角色改用 Student Capability View，包含：

- Harness 身份；
- Student Model 可见 Tool 的名称与一句话能力；
- Output Contract 接受的动作类型；
- 已注册 Extension 的身份、Lifecycle Phase 与可能影响的 Student 可见对象；
- Prompt 和 Output Component 是否已注册，但不提供正文或源码。

不包含 entrypoint、路径、Python 源码、原始 Component Configuration、Prompt 正文或 Hook
hidden state。注册只证明能力可用；实际 Invocation 与 Change 必须由 Trajectory Evidence
证明。

Failure Analyst 不分担 Hypothesis Researcher 的组件归因职责。它只使用 Capability View
区分“能力不可用”和“能力存在但 Student 没有使用”等明显混淆因素。

## 7. Hypothesis Researcher Behavior Interface

Hypothesis Researcher 需要同时看到声明的 Student 行为接口与引用 Trajectory 中的实际
有效上下文。Student Behavior Interface 包含：

- 完整的 Model-visible Prompt 内容；
- 完整的 Model-visible Tool Definition，包括名称、描述和参数 Schema；
- Output Contract 接受的动作与 invalid-output feedback 行为；
- Extension 的身份、Lifecycle Phase、可读 State、可写 State 与声明用途。

不包含 Component 文件、Python 源码、entrypoint 或 Compiler 实现选择。Behavior
Interface 描述理论上提供的行为边界；Trajectory Change 描述某次 Run 中实际发生的影响。

本轮不增加 `InterventionHypothesis` 字段。现有 `phase_plan[].instruction` 必须明确：

1. 要改变的 Student-visible 信息或控制语义；
2. 改变后的具体含义；
3. 不指定 Component 文件、Python 实现或未经支持的 Runtime 能力。

`post_prompt` Intervention 可以临时验证 Prompt 语义变化。Trial 成功只证明 Student 行为
对该控制信号敏感，不自动证明现有 Prompt 是根本原因。

## 8. 已确认的后续设计

Intervention Worker 第二轮影子实现采用：

- 把不变的 Active Observation 只放在 activation message 中，删除重复查询工具；
- 用表格列出 Editable Context；
- 用短头部加未转义精确正文读取单个 Block；
- 统一未知 Block 的模型可见错误格式。

Trial Reviewer 后续影子实现应：

- 用围绕冻结 Phase 的 Trial Judgment View 替代三条平铺完整事件目录；
- 并列 Source 与 Branch 的立即 Student Action；
- 复用 Context Change 表达实际 Worker 修改；
- 默认只给相关 Event Index，精确 Event 按需读取。

Intervention Worker 内容已通过独立 A/B 实现与验证；Trial Reviewer 内容仍不属于当前
代码实施范围。

## 9. Focused Probe

### 9.1 离线投影检查

使用既有 Incumbent Evaluation 与含 Extension 的 Student Rollout Artifact：

- 比较旧/新 Tool Output 字符数；
- 验证默认视图不含 `metadata.results` 和 `omitted`；
- 验证每个 `STUDENT_VISIBLE` Block 都能在对应 Model Input 中找到；
- 验证每个 Change 的 source/effective 映射可回溯；
- 验证长内容可按引用搜索和分段读取；
- 验证底层 Artifact 未发生任何修改。

### 9.2 真实 API 角色检查

对相同输入默认各运行三次：

- Teacher Judgment：检查 `score + assessment` 输出稳定性和 assessment 长度；
- Failure Analyst：检查是否仍形成有直接 Evidence 的行为诊断，且不越界提出机制；
- Hypothesis Researcher：检查是否能识别 Prompt、Tool、Output 或 Extension 等候选语义
  表面，并给出可由 Intervention Executor 执行的 `instruction`。

### 9.3 验收条件

- 影子实现不修改正式 Teacher Harness Template 和正式 Tool Registry；
- 结构化 Role Output 校验成功；
- 三次重复没有出现系统性的 Evidence 缺失或职责越界；
- 新视图显著减少重复内容，同时保留完成角色职责需要的精确下钻路径；
- Student-visible、Runtime-only 和 Derived View 没有混淆；
- 实验失败保留 transcript 和 Artifact，不通过修改中间产物强制推进。

## 10. 实施顺序

1. 建立影子投影模块、影子 Teacher Template 与独立 Focused Probe 脚本；
2. 为 Evaluation Case、Trajectory、Capability View 和 Behavior Interface 编写小型测试；
3. 使用既有 Artifact 运行离线投影和字符数比较；
4. 使用真实 API 分别运行 Teacher Judgment、Failure Analyst、Hypothesis Researcher；
5. 汇总旧/新结果，不切换正式工具；
6. 根据实验结果决定是否进入正式迁移任务。

## 11. 影子实施记录

### 11.1 已实现内容

- `experiments/teacher_query_views/` 包含确定性视图、影子 Tool Factory、Judge
  影子协议和 Failure Analyst/Hypothesis Researcher 副本模板；
- `experiments/run_teacher_query_views_probe.py` 提供 `offline` 与 `api` 两类独立
  Probe，并允许真实 API 只复测指定角色；
- `tests/experiments/test_teacher_query_views.py` 覆盖 Evaluation Case、Context
  Revision、Block 精确读取、Runtime-only 搜索、Extension Change、Capability
  View、Behavior Interface 和 Judge 输出协议；
- 正式 Tool Registry、正式 Teacher Harness Template、Evaluation Report 和 Student
  Rollout Artifact 均未修改。

### 11.2 离线结果

最终离线结果保存在
`runs/experiments/teacher_query_views/20260812_offline_v4/summary.json`：

- 75 个 Evaluation Case 的模型可见字符为原始 JSON 的 `28.83%`；
- 225 条 Student Trajectory 的模型可见字符为原始记录的 `13.49%`；
- 含真实 Extension Change 的样本由 `69196` 字符降为 `7038` 字符；
- `metadata.results` 与固定 `omitted` 均未进入新 Trajectory View；
- Change 的 effective Block 已由后续 Model Input 验证为 `STUDENT_VISIBLE`；
- 所有源 Artifact 的 SHA-256 在 Probe 前后一致。

### 11.3 真实 API 结果

最终有效角色结果分别保存在：

- `runs/experiments/teacher_query_views/20260812_api_v2/`：修正后的 Failure
  Analyst 与 Teacher Judge 三次重复；
- `runs/experiments/teacher_query_views/20260812_researcher_v3/`：最终 Hypothesis
  Researcher 三次重复。

结果如下：

- Teacher Judge 三次均一次返回有效 `score + assessment`，评分一致，assessment
  长度为 85 至 114 字符；
- Failure Analyst 三次均完成并形成直接引用 Trajectory 的行为诊断；加入简短读取
  说明后，没有再把旧 Artifact 的 `assessment=unavailable` 误解成评分结论；
- 三次 Hypothesis Researcher 均读取全部四条 Evidence Trajectory、至少一次 Student
  Behavior Interface 和能力目录，并提交结构有效的 Intervention Hypothesis；
- Researcher 两次选择单阶段 `pre_final`，一次选择
  `post_tool -> pre_final`，三者均明确 Student-visible 信息或控制语义的变化；
- Researcher 有两次首次提交即通过；另一次 `applicability` 为 309 字符，超过 300
  字符上限后经既有修复反馈通过。这是仍存在的结构化长度遵循波动，不是查询视图
  Evidence 缺失。

Failure Analyst 仍有独立的 Output Contract 遵循波动：三次均最终成功，但其中两次
需要修复过长的 `pattern`/`applicability`，一次还曾把完整 Evidence Reference 缩写后被
校验拒绝；另一次在重复读取时触及六条唯一 Trajectory 的预算。现有反馈均能恢复，且
这些失败没有显示查询视图缺少 Evidence，但它们不应被误记为“一次提交稳定通过”。

### 11.4 当前结论

影子实现满足本轮“保留底层 Artifact、精简角色视图、提供精确下钻、真实角色可运行”
的验证目标。当前没有把影子工具切换为正式工具，也没有删除旧查询接口。正式迁移和
旧工具清理应作为下一阶段独立决定；Mechanism Distiller 仍不在本轮实施范围。

## 12. 正式方案与影子方案 A/B

### 12.1 方法

A/B 结果保存在
`runs/experiments/teacher_query_views/20260812_ab/summary.json`。每个重复使用相同的
历史 Role Input、Resource Config、Teacher API 配置和 Role Budget，并发启动正式与影子
方案；三个重复依次执行。实验只调用 Failure Analyst 和 Hypothesis Researcher 的
Teacher API，没有启动 Student、Intervention Executor 或 Evolution Controller。

该实验比较的是两套当前完整方案。影子角色不仅改变查询视图，也包含本轮已确认的角色
提示调整，因此不能把所有差异严格归因于 Tool Output 排版。

### 12.2 结果

| Role | Scheme | Completed | Mean model turns | Mean query calls | Mean Tool Result chars | Mean input tokens | Mean total tokens | Mean submit retries |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Failure Analyst | formal | 3/3 | 8.00 | 13.33 | 148307.67 | 227001.00 | 237728.33 | 1.33 |
| Failure Analyst | shadow | 3/3 | 8.00 | 18.00 | 76107.67 | 147416.33 | 158580.00 | 1.00 |
| Hypothesis Researcher | formal | 3/3 | 5.67 | 5.00 | 90959.00 | 176857.00 | 194354.67 | 2.33 |
| Hypothesis Researcher | shadow | 3/3 | 5.00 | 11.33 | 50341.33 | 111389.33 | 129704.33 | 1.33 |

影子方案相对正式方案：

- Failure Analyst 查询调用增加 `35.0%`，平均模型回合不变；Tool Result 字符减少
  `48.7%`，输入 token 减少 `35.1%`，总 token 减少 `33.3%`；
- Hypothesis Researcher 查询调用增加 `126.6%`，平均模型回合减少 `11.8%`；Tool
  Result 字符减少 `44.7%`，输入 token 减少 `37.0%`，总 token 减少 `33.3%`；
- 两侧全部在 `max_turns=20` 内完成。Failure Analyst 的实际范围为正式 `6..11`、
  影子 `7..9`；Researcher 为正式 `5..6`、影子 `4..6`；
- 单次查询的平均 Tool Result 字符从 Analyst 的 `11123.1` 降到 `4228.2`，从
  Researcher 的 `18191.8` 降到 `4441.9`。

当前 Provider 在 `parallel_tool_calls=False` 时仍返回了每条 Assistant Message 最多
四至七个 Tool Calls，Runner 会在同一模型回合执行多个非终端调用。因此本次实验中
“查询次数增加”没有按一比一关系消耗模型回合。这是实际观察，不是可跨 Provider 假设；
其他 OpenAI-compatible API 若严格限制每个响应一个 Tool Call，分层读取可能显著增加
`max_turns` 压力。

### 12.3 工具使用观察

- `get_trajectory_block` 是有效的主要下钻接口：Analyst 三次共调用 10 次，Researcher
  共调用 15 次；
- Researcher 三次均调用 Student Behavior Interface；Analyst 仅一次需要 Capability
  View，符合其条件式使用职责；
- `get_trajectory_change` 与 `search_hidden_trajectory_blocks` 在本组 Baseline Artifact
  中没有被调用，因为引用轨迹不包含 Extension Change，不能据此判定它们没有价值；
- 一次影子 Researcher 在没有 Trial 资源时误调用 `list_trial_evidence`，收到明确工具
  错误后恢复；这与 Trajectory 拆分无关，但说明 Tool 可用性仍可进一步按 Role Session
  条件收窄。

### 12.4 A/B 结论

工具拆分确实增加了查询调用数量，但在当前 Provider 上没有减少实际回合预算余量，且
显著降低了每次返回、累计输入和总 token。当前证据支持保留“默认 Trajectory + 精确
Block 下钻”的分层方式，但不能据此认为任意进一步拆分都没有代价。正式迁移前仍需把
“每响应只允许一个 Tool Call”作为兼容边界，决定是保留更高 Role Turn Budget、允许安全
的批量只读查询，还是合并极高频的目录与首段读取操作。

## 13. Researcher 与 Intervention 扩展 A/B

### 13.1 Researcher 跨失败模式复测

使用 `20260809_base` 中两类既有 Failure Analyst 结论：

- 第一次检索遗漏问题所需实体或关系，Student 仍直接提交答案；
- `topk=1` 的属性检索未返回出生信息，Student 直接提交无法确定的非答案。

每类输入对正式方案和影子方案各运行五次，共 20 次真实 DeepSeek Role Run。合并摘要
保存在
`runs/experiments/teacher_query_views/20260812_researcher_ab_multi/researcher_combined_5x_summary.json`。

| Scheme | Completed | Mean turns | Mean queries | Mean Tool Result chars | Mean input tokens | Mean total tokens | Mean submit retries |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formal | 10/10 | 5.20 | 4.50 | 55301.00 | 115672.80 | 130439.90 | 2.20 |
| shadow | 10/10 | 3.90 | 7.20 | 30935.60 | 58086.80 | 71635.50 | 0.20 |

影子方案的查询次数增加 `60.0%`，Tool Result 字符减少 `44.1%`，输入 token 减少
`49.8%`，总 token 减少 `45.1%`。两套均能生成结构有效且可由现有 Worker 执行的
Hypothesis；影子方案减少的主要是结构化提交修订，而非必要 Evidence 阅读。

阶段选择仍有真实方差。遗漏实体/关系样本中，正式方案选择 `pre_final` 两次、
`post_tool` 三次，影子方案选择 `post_tool` 三次、`pre_final` 两次；属性缺口样本中，
正式方案选择 `post_tool` 四次、`pre_final` 一次，影子方案选择 `post_tool` 三次、
`pre_final` 两次。两种阶段都属于现有能力边界内的可证伪方案，因此不能把这种差异
归因为视图丢失；它反映同一 Failure Pattern 存在多个合理干预点。若 Controller 要求
唯一阶段，需要另行收紧研究协议或加入选择准则。

本组 Researcher A/B 仍比较两套完整影子方案：影子侧同时包含已确认的提示调整和查询
视图，不能把全部收益严格归因于 Tool Output 排版。影子侧 10 次中有 3 次工具输入
错误，均为 Provider 生成了截断 JSON 参数并在后续回合恢复；正式侧没有查询工具输入
错误。这是 OpenAI-compatible Tool Calling 的独立稳定性边界。

### 13.2 Intervention Worker 视图隔离复测

使用同一 Hypothesis 下两个保存的 Trial：一个应在 `post_tool` 修改上下文并促使下一步
检索，另一个因现有证据已覆盖问题而应正确不干预。每个 Trial 对正式与影子 Worker
各运行三次，共 12 次 Worker Run 和 12 次 Student Branch Run。完整摘要保存在
`runs/experiments/teacher_query_views/20260812_intervention_ab_deepseek/summary.json`。

本组使用完全相同的 Worker Prompt、Role Input、Student Prefix、Teacher/Student 配置
和终端修改工具，只替换只读查询视图，因此比 Researcher A/B 更接近视图隔离实验。

| Scheme | Worker runs | Correct positive action | Correct no-op | Mean queries | Mean Tool Result chars | Mean total tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| formal | 6 | 3/3 | 3/3 | 4.17 | 4696.67 | 12758.83 |
| shadow | 6 | 3/3 | 3/3 | 3.67 | 4441.00 | 11831.50 |

正触发样本中，两套均三次执行 `apply_context_patch`；修改后 Student 的下一动作均为
`search`，六个 Branch 均由 Teacher Judge 判为正确。正确不触发样本中，两套均三次
执行 `continue_without_change`。该样本最终分数存在 Student 采样波动，正式为 1/3、
影子为 2/3，但两侧 Worker 决策和 Student 的立即动作完全一致，不能把分数差异归因于
查询视图。

影子视图平均减少 `12.0%` 查询调用、`5.4%` Tool Result 字符和 `7.3%` Worker 总
token。收益小于 Researcher，因为 Worker 的精确检索结果正文占主体，不能在不损失
判断 Evidence 的前提下继续摘要。删除重复 Active Observation 和使用紧凑 Block 目录
仍有稳定的小幅收益。

两套 Worker 都观察到“一次响应并发多个工具”而收到单工具约束反馈；正式每次平均
2.0 条、影子 1.33 条。这些不是 Block ID 或视图解析错误，且均能恢复，但说明该角色
对 Provider 的 `parallel_tool_calls` 遵循仍不稳定。源 Trial 的运行前后 SHA-256 一致，
实验没有修改既有 Artifact。

### 13.3 当前迁移判断

现有证据支持正式迁移以下视图原则：Researcher 保留默认 Trajectory 与精确 Block
下钻；Intervention Worker 删除重复 Active Observation 查询，使用紧凑 Editable
Context 表格和未转义精确 Block。正式切换仍应作为独立变更进行，不在影子实验中删除
旧工具。阶段选择多解和 Provider Tool Calling 稳定性不应通过继续压缩 Tool Result
解决。

## 14. Reviewer 影子接入结果

Trial Reviewer 与 Evidence Reviewer 的补充 A/B 记录见
`docs/audits/teacher-query-views-reviewers-ab-20260812.md`。本轮没有提高通过率，不进入
正式迁移：

- Trial Reviewer 正确不触发样本能从紧凑默认视图受益，但正触发样本会自由读取大量
  后续事件，抵消压缩并增加立即动作混淆风险；
- Evidence Reviewer 没有查询工具，输入混合视图使平均总 token 下降约 `19.3%`，但
  首次提交通过率未提高；失败仍是自由文本超过 Output Contract 长度上限；
- 两者最终均能在预算内恢复，且 Evidence Reviewer 的总体 Decision 与正式方案一致，
  但这不足以授权切换正式视图。

Trial Reviewer 影子方案现已放弃并删除实现，仅保留历史实验 Artifact；不再沿当前
`get_trial_evidence + get_trial_event` 设计继续打补丁。

Evidence Reviewer 随后使用另外四份 Artifact 覆盖 `continue`、
`ready_to_distill`、`reject`、`revise` 做交叉复测，共计 18 对正式/影子运行。影子首轮
prompt token 稳定下降约 `15.2%`，合计平均总 token 下降约 `19.9%`，但中位数只下降
`11.2%`，并且四组输入中有两组成本反向增加；Decision 配对一致 `15/18`，phase status
一致 `16/18`。因此约 `20%` 只能作为受重试波动影响的总体均值，不能视为稳定收益，
Evidence Reviewer 也暂不正式迁移。完整记录仍见上述 A/B 报告。

## 15. Mechanism Distiller Evidence Dossier A/B

### 15.1 影子设计

Distiller 不是单一判断角色：它需要综合 Evidence Review、逐 Trial 因果证据、实际
Student-visible 干预、预算和运行时能力，再用草稿工具形成可编译 Mechanism。正式实现
要求模型先调用 `list_trial_evidence`，再逐条读取 `get_trial_evidence`；同一 Trial 的
Review、执行事实和结果散布在初始输入与 Tool Result 中，完整事件目录又带来大量并非
Distiller 默认需要的上下文。

影子实现没有摘要替代证据，而是在初始输入提供一份完整的角色专用
`Distillation Evidence Dossier`：

- 原样保留冻结 Hypothesis、Evidence Review、Coverage、Budget、Capability Constraints；
- 每个 Trial 用同一条紧凑记录对齐 independent Review、Worker result、实际
  Student-visible action payload、activation budget/count、确定性 phase effect 和压缩后的
  source/branch outcome；
- outcome 保留 status、score、score source、static decision、exact match、steps 和
  tool calls，不重复 model calls、完整 token metadata 或原始事件目录；
- `get_distillation_trial_detail(trial_ref)` 只在 dossier 存在实质冲突、事件边界缺失或
  mutation 歧义时返回完整事件目录与原始 change；
- Mechanism draft、Hook evaluator probe、validation 和终态协议与正式实现完全相同。

底层 Trial、原始轨迹和 Provider metadata 均未修改。影子模板位于
`experiments/teacher_query_views/templates/mechanism_distiller/`，A/B 入口为
`experiments/run_distiller_dossier_ab.py`。

### 15.2 真实 API 实验

实验对每一对正式/影子 run 使用相同保存的 Role Input、Resource Config、Teacher API、
角色预算、Output Contract 和 Student-profile Hook probe。正式与影子并发启动；源 Role
Artifact 与 Trial 文件运行前后 SHA-256 一致。

第一组使用 `20260809_base` 的 4 Trial `post_tool` 对比机制。因两侧均出现本机
Student-profile Hook probe 的 `WinError 10061`，最初 3 对只记录为基础设施无效预跑，
不进入质量和完成率结论。确认 Ollama `qwen3:8b` 可调用后重新执行 3 对，并因一次影子
终态字段重试把同一输入补到正式/影子各 5 次：

| Scheme | Completed | First-submit passed | Mean evidence queries | Mean total tokens | Mechanism direction |
| --- | ---: | ---: | ---: | ---: | --- |
| formal | 5/5 | 5/5 | 5.0 | 308682.40 | 5/5 单一 post_tool + hook_model + one-shot note |
| shadow | 5/5 | 4/5 | 0.0 | 118678.60 | 5/5 单一 post_tool + hook_model + one-shot note |

影子总 token 为正式版的 `38.4%`，约减少 `61.6%`。唯一一次重试是提交
`next_obligation: "null"` 字符串而非省略字段，模型在下一回合修复；它不涉及 dossier
缺证据或 Mechanism 语义改变。5 次影子 run 均未调用异常详情工具。

第二组使用 `20260807_debug` 的 5 Trial `pre_final` 验证检索机制；该输入预算耗尽且
`conclusion_required=true`：

| Scheme | Completed | First-submit passed | Mean evidence queries | Mean total tokens | Mechanism direction |
| --- | ---: | ---: | ---: | ---: | --- |
| formal | 3/3 | 3/3 | 6.33 | 417138.00 | 3/3 单一 pre_final + hook_model + one-shot defer |
| shadow | 3/3 | 2/3 | 0.0 | 159031.67 | 3/3 单一 pre_final + hook_model + one-shot defer |

影子总 token 为正式版的 `38.1%`，约减少 `61.9%`。同样只有一次
`next_obligation: "null"` 终态格式重试。两侧都保持 3 个正触发、2 个正确不触发、未
观测 uncertain、3/3 正触发后下一动作是 Search、2/3 得分改善而 1/3 拒答无收益、只
声明过程效果以及预算耗尽时必须下结论等边界。

### 15.3 判断

在两个不同机制方向、共 16 个有效真实 Role Run 中，正式与影子最终完成率均为
`100%`，Mechanism 的 phase、evaluator 类型、action 类型、activation budget、证据
覆盖和 known limits 一致。影子首次提交为 `6/8`，正式为 `8/8`；两次差异均是相同的
可恢复终态空值编码错误，而非证据或草稿校验失败。因此现有证据支持“最终稳定性保持”，
但不支持声称过程首次提交稳定性优于正式版。

清晰度和全面性有实际提升：每条 Trial 的判定、实际修改、直接后继动作和结果不再跨
多次 Tool Call 对齐；完整 Review 与精确 Student-visible payload 得到保留；不相关的
累计轨迹、重复 metadata 和完整事件目录被移出默认视图，仍可按 Trial 精确下钻。模型
在 8/8 影子 run 中不需要下钻，且都生成了包含正负覆盖、三值边界、guard/predicate
分工、action、fallback、state、观测项和限制的完整 Mechanism。

该阶段的结论曾是保留影子实现作为正式迁移候选。后续迁移已完成：Evidence Dossier
进入正式 Distiller，固定 Hook probe 由通用 Student Model Experiment 取代，影子实现
本身已经删除。终态可选空字段造成的 Provider 重试仍作为输出协议问题单独记录，不归因
于 Evidence View。

## 16. 正式主链路迁移进度

本节只记录已经进入正式代码并完成定向测试与真实 API 验证的项目；尚未完成的项目保持
未勾选，不据此宣称主链路已经具备对应能力。

- [x] Teacher Judge：正式输出 `score + assessment`。
- [x] Failure Analyst：Evaluation 与 Trajectory 角色视图。
- [x] Hypothesis Researcher：分层证据视图与 Student Behavior Interface。
- [x] Intervention Worker：紧凑 Editable Context 与精确 Block View。
- [x] Mechanism Distiller：Distillation Evidence Dossier。
- [x] Hook-model 研究：通用 Student Model Experiment 取代固定 Probe。
- [x] Compiler：native API 视图、packet 去重、continuation 投影和实验交接。
- [x] Conformance Reviewer：按 Example 批处理、独立轨迹边界与 Hook-model 成本预检。
- [x] Candidate Reviewer：配对 Case、Behavior Trajectory 与按需长文本视图。
- [x] 清理：删除已合并影子副本及实验确认较差的角色实现。

Trial Reviewer 与 Evidence Reviewer 的影子方案不进入正式主链路；Compiler 只吸收已经
独立证明有价值的工程设施，不整体迁移影子行为模板。每项迁移完成后均使用相同输入重复
三次真实 Teacher API 验证，并把结果追加到本节。

### 16.1 Teacher Judge

2026-08-14 已将影子验证过的严格输出契约迁入正式 `TeacherBinaryJudge`。Judgment 新增
简短 `assessment`，同时继续保存 `raw_output`、usage 和 provider metadata；解析器要求
响应仅包含 `score` 与非空 `assessment`，拒绝从夹杂文本中宽松提取分数。评估层 22 项
单元测试通过。

使用正式 DeepSeek Teacher、关闭 thinking，对互相矛盾实体、地理上下位关系、
`approximately` 零容差三个边界案例整组重复 3 次，共 9 次真实调用。9/9 均一次生成
合法协议、9/9 判为 0，且 assessment 分别明确指出矛盾实体、broader location 不是
alias、数值容差为 0；单次总 token 为 311--320。未观察到协议重试或判分漂移。

### 16.2 Failure Analyst

2026-08-14 已将紧凑 Evaluation Case、Block/Revision Trajectory、Extension Change、
精确 Block 下钻和 Runtime-only 搜索迁入正式工具。完整 `get_harness_manifest` 从 Analyst
模板移除，替换为只呈现 Student 可观察工具、Extension phase 与 action surface 的
`get_student_capability_view`；Analyst 仍只做行为诊断，不承担组件级归因。底层 Evaluation
与 Rollout Artifact 未改。27 项角色装配、资源访问和视图测试通过。

使用 `20260812_ab` 相同保存输入先执行 6 次真实 API 迁移诊断，确认 6/6 最终完成，
同时如实暴露了字段贴近 Schema 上限、截短 evidence ID 和超出 6 条唯一轨迹预算等提交
不稳定。随后只补明既有长度安全余量、完整 ID 复制和证据预算规则，再执行最终 3 次：
3/3 完成、3/3 第一次提交通过、无 Tool error；每次读取 5--6 条轨迹，最终引用覆盖
2--3 个逻辑案例。三次均收敛到“检索未建立问题所需关系或属性时即终答、没有针对缺口
继续检索”的同一行为方向，总 token 分别为 `104515`、`179234`、`133330`。结果支持
正式迁移，但也表明多轨迹分析和 thinking 仍是主体成本，视图压缩不等于低延迟。

### 16.3 Hypothesis Researcher

2026-08-14 已将与 Analyst 相同的 Context Revision、Extension Change、Block 下钻和
Runtime-only 搜索接入正式 Researcher，并新增 `get_student_behavior_interface`：只有先读
对应轨迹后才能读取该轨迹实际送入 Student 的 system/developer prompt、model-visible
工具声明、输出动作表面和 Extension phase/read-write surface。Capability registration
与实际轨迹行为继续分开呈现；底层 Artifact 和 Researcher 的证据 allowlist 未变。角色
装配、续接 transcript 和资源账本定向测试通过。

使用 `20260812_ab` 保存的同一 Researcher 输入执行 3 次真实 API。3/3 完成，3/3 读取
全部 4 条冻结轨迹、Student Behavior Interface 和 intervention capability catalog；三次
均生成单一 corrective `pre_final` 方案，并把缺失关系/属性、同名实体混淆、passage-supported
排除项和额外正负覆盖写入可观察条件。总 token 为 `124512`、`201617`、`162802`。
首次提交通过为 1/3；其余两次只因 activation/applicability 贴近 Schema 长度上限而修复，
最终 phase 和语义方向未漂移。由此支持视图正式迁移和最终稳定性，但不宣称首提格式已经
完全稳定。

### 16.4 Intervention Worker

2026-08-14 已将正式 Worker 的 Editable Context 目录改为紧凑有序表格，单 Block 读取改为
无 JSON 转义的精确内容边界；未知 Block 返回统一的结构化错误标识。每次 Hook activation
的 user message 已直接携带程序维护的 active observation，因此从 native tool list 删除
重复的 `inspect_active_observation`，不删除底层 observation 或审计 trace。所有写工具、
phase action 和 patch 校验逻辑保持不变。19 项 Intervention 生命周期测试通过。

复用 `20260809_base` 的同一 `post_tool` Trial，使用正式 DeepSeek Worker、真实本地
Student 和 Teacher Judge 重复 3 次。3/3 均用 1 次 Context 目录读取、1 次精确 Block
读取和 1 次 `apply_context_patch` 完成，无 Tool error；3/3 patch 实际进入 Student
上下文，Student 紧随其后的动作均为 `search`，最终 branch score 均为 1。Worker 每次
3 个模型回合，总 token 分别为 `8586`、`9131`、`8971`。这一结果同时验证了查询视图
可读性和真实分支副作用，没有仅凭 Worker 自述判定通过。

### 16.5 Mechanism Distiller

2026-08-14 已将 Distillation Evidence Dossier 接入正式 Prompt：冻结 Hypothesis、Evidence
Review、Coverage/Budget、每条独立 Trial Review、实际 Student-visible mutation、activation、
deterministic phase effect 和 outcome 在初始输入中按 `trial_ref` 对齐。原先三个通用 Trial
目录/读取工具从 Distiller 模板移除，保留一个按引用返回完整事件目录的
`get_distillation_trial_detail` 异常下钻工具。Mechanism draft、constraints 和 validation
工具未在本阶段改变。正式装配与 dossier/detail 投影测试通过。

使用 `20260809_base` 的 4 Trial 保存输入执行 3 次真实 API。前两次不调用详情工具，均以
一套 draft/phase/constraints/probe/validation 序列生成 `mechanism_001`；总 token 为
`158190`、`112108`。第三次固定 Hook probe 将同一个冻结 positive fixture 稳定误判为
negative；Distiller 连续尝试 3 个更操作化 draft 后只下钻该冲突 Trial，最终合理返回
`needs_evidence`，总 token `365577`。因此 dossier 的正常/异常披露路径均按设计工作；
第三轮差异来自现有固定 probe 对 Hook model 的非稳定标签，而非 evidence view 丢失。
这一结果支持 dossier 正式迁移，同时直接形成下一阶段“用通用 Student Model Experiment
取代固定 pass-like probe”的问题证据。

### 16.6 Student Model Experiment

2026-08-14 已删除固定 `probe_mechanism_evaluators` 及其程序所有的 expected label、
match rate 和隐式通过语义，改为 Distiller 与 Compiler 共用的
`run_student_model_experiment`。Teacher 自行提供实验目的、system prompt、1--6 个输入、
thinking mode 和 1--3 次重复；正式 artifact 保留逐请求原始输出、usage、错误和 provider
metadata，工具视图只省略 provider metadata，不计算正确率或替角色选择 thinking mode。
Distiller 产物中的实验会原样交接给 Compiler。`HookModelRequest` 同时新增可选的
`thinking_mode=enabled|disabled`，由 OpenAI-compatible provider 在单次请求层映射，不改变
Student 正式 rollout 的默认模式。

直接使用 Student profile 执行 2 个案例、2 种 thinking mode、每项 3 次，共 12 次真实
调用，12/12 返回成功；同一案例的标签在重复调用间会漂移。当时框架把 Ollama `/v1`
的 `disabled` 错误映射为原生 API 字段 `think: false`，该字段被 OpenAI-compatible endpoint
忽略，因此返回中仍有 reasoning metadata。2026-08-15 已改为
`reasoning_effort: "none"` 并通过重复实验确认关闭生效；原实验仍支持删除 expected-label
程序硬门禁，但不能再作为“Ollama 无法关闭 thinking”的证据。

正式 Distiller 在通用工具接入后的初次 3 次验证均成功，但有两次进行了过量 prompt
迭代：一次在长度错误后执行 20 个 observation，另一次连续两轮共执行 48 个 observation。
随后明确实验只服务于重要的不确定性、通常至多调用一次且不因表面标签一致继续调参，
再用相同 artifact 重复 3 次：3/3 一次提交、无 Tool error、3/3 `distilled`；两次跳过
实验，一次执行单一 disabled-mode 实验，共 10 个 observation，总 token 分别为
`154766`、`109465`、`101375`。该次仍使用了 5 个案例，超过 prompt 建议的 1--3 个但未
违反工具的 1--6 个硬边界，说明软指导显著减少了迭代，却不能保证严格实验规模。

旧实验第三次运行的两轮 prompt 调优另见对应
`prompt_iteration_analysis.md`。它表明 Distiller 能识别危险的 `negative -> positive`
误触发并收紧操作边界；修订后剩余漂移只发生在共同 no-op 的 `negative/uncertain` 之间。
因此最终机制通过的依据是错误后果被安全化并写入 known limits，而不是分类器已经完全
稳定。

### 16.7 Compiler

2026-08-14 保留正式 Compiler 的完整 system prompt、完整 `CompilerInput`、workspace
写工具、finalizer 和终态协议，只迁入四项独立设施。第一，`query_hook_api` 默认返回
Python-native contract，不再同时复制结构化 contract。第二，capability packet 中已经
由 Runtime Input Topic native 文档覆盖的 symbol 不再作为 JSON contract 重复出现；
packet selection 只保留 API 输入选择和未解析项，不复制 Mechanism 中已有的 guards、
decision contract、fallback 与 activation budget。第三，初始资源上下文直接提供当前
manifest、evolution policy、Extension 索引；Compiler revision 续接时还提供该 Candidate
的精确 changed file 内容。第四，Distiller 的 `student_model_experiments` 原样进入
`CompilerInput`，Compiler 也可按需运行同一个描述性工具。未迁移影子 Compiler 的完整
Implementation Brief、自动 reference 选择或影子角色模板。

生产视图、continuation materialization、API query 以及现有 Compiler resource 共 22 项
定向测试通过。使用 `20260809_base` 同一历史 Compiler 输入执行第一组 3 次真实 API：
3/3 提交、3/3 首次 finalizer 通过、3/3 deterministic validation 通过；因旧 A/B 入口未
传递 Student profile 环境，三次可选实验均明确失败后继续实现，这组只用于验证
Compiler/validation，不用于实验交接。该入口随后补齐 `.env` 资源映射。

修正入口后再次执行 3 次：3/3 提交、3/3 首次 finalizer 通过、3/3 deterministic
validation 通过；1/3 运行 3 个案例、enabled/disabled 各一次的实验并在实现摘要中引用
观察，2/3 未额外实验。首轮 prompt token 三次均为 `9344`，相对旧正式同案例的
`12413` 减少 `24.7%`；平均总 token 为 `347741`，与旧正式 `342743` 相近，不能宣称
总体成本下降。实际 API rejected query 为 `2/5/1`，平均 `2.67`，低于旧正式平均
`4.33`，但没有归零；实验统计器原只识别 JSON 返回，已修正为同时识别 native text，
不回写现有 summary。

本阶段只能证明 authoring、实验交接和机械合法性保持稳定。三份 Candidate 是否忠实执行
Hook-model 决策边界仍需 Conformance Reviewer 检查，不能由 HarnessValidator 的通过替代。

### 16.8 Conformance Reviewer

2026-08-14 已将正式 Conformance Review 从“同一 Example 的每条 replicate 各调用一次”
改为“同一 Example 一次调用、按 replicate 返回有序独立 Finding”。Mechanism 与完整
reference observations 在输入中只呈现一次，每条 `candidate_trajectory_view` 使用明确的
标题和紧凑 JSON 边界；底层 replay 与 reference artifact 不删除信息。输出协议升级为
`conformance_review_batch@5`，程序严格校验 replicate 顺序，再附加权威 trial/run identity
并确定性聚合。Runner error 仍由程序直接形成 `runtime_error` Finding。

角色输入新增每条 rollout 的 Hook-model 调用次数、profile、purpose、`thinking_mode` 与基础
token 事实。Reviewer 只预检 Mechanism 明示的 profile、调用上限、activation budget 和
thinking 选择；没有明示 token 上限时，不用单条 token 数替代后续 Candidate 成本比较。
Prompt 同时区分“必须执行的 Harness action”与“随后观察到的 Student effect”：后续正确
搜索不能补偿 intervention 本身仍输出占位符或缺少 Mechanism 要求的具体内容。

定向的角色协议、投影、checkpoint、重试和 Controller 测试共 70 项通过。随后复用历史
Candidate replay 中一组边界较难的 3 条轨迹重复调用正式 DeepSeek Teacher 3 次，不重跑
Student。三次均一次提交，且 9/9 Finding 一致判为
`implementation_mismatch/action -> implementation`，准确指出三条 intervention 都把具体
缺失实体/关系退化成占位式文本；assessment 均低于 1000 字符。三次总 token 分别为
`18762`、`17720`、`16722`，相对迁移前同输入的 `49251`、`49220`、`48306` 下降约
`62%--66%`。迁移前第三次曾整体误判为 `faithful`；显式 replicate 边界和 action/effect
判据补正后未再出现该翻转，因此正式迁移通过。

### 16.9 Candidate Reviewer

2026-08-14 已将六项验证过的证据设施接入正式 Candidate Reviewer。初始 brief 只呈现一次
Mechanism、压缩 Conformance、Incumbent/Candidate 指标对比和 change landscape，不把
Candidate Validation Report 与重复 metrics 塞入模型上下文。`list_candidate_changes` 默认
changed-first 且最多一次显示 100 条；`get_candidate_case` 以 replicate 配对 score、answer、
执行和基础 token delta，并增加逐 replicate Hook decision/change 轻量索引；
`get_paired_student_trajectory` 只呈现行为与 Hook effect 事件，删除累计 model input、provider
metadata、reasoning、`metadata.results` 与 `omitted`；Harness diff 小型时完整呈现，大型时按
path 下钻；新增 `get_candidate_trajectory_text` 供 preview 不足时精确读取单个长文本字段。
底层 Evaluation、Rollout 和 Candidate Template Artifact 均未裁剪。

Prompt 要求先用 Case 的 outcome/Hook activity 选择混合或异常 replicate，再读取 paired
trajectory；存在 improved/regressed 时仍由程序强制至少各读取一条配对轨迹。`revise` 只适用
于完成一个 bounded obligation 后同一 Candidate 可能成为可晋升对象；如果独立的终止理由
仍然成立，Reviewer 必须 `reject`，不能用另一项局部缺陷推迟已有结论。

正式装配、视图与资源义务共 18 项定向测试通过。第一轮 3 次真实 API 为
`reject/revise(implementation)/reject`；分歧来自 Case 视图未预先展示同一 boundary 的混合
Hook 标签，模型随机读取不同 replicate。增加 Hook activity 索引并明确 revise/reject 支配
关系后，复用同一 `20260809_base` Candidate Evaluation 和 rollout 再运行 3 次，3/3 均为
`reject`。三次都观察到目标正向路径，同时一致指出越界正触发、平坦的 aggregate accuracy
和约 `93%` 的额外总 token 成本需要至少两个独立重设计。平均查询返回字符约 `108886`，
相对迁移前正式 A/B 的约 `450152` 降低 `75.8%`；平均总 token 约 `225681`，相对约
`287312` 降低 `21.5%`。其中一次首提因尚未读取 regressed paired trajectory 被程序拒绝，
补读后结论不变，证明证据义务按预期工作。
