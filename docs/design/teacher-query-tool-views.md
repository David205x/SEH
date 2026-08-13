# Teacher 查询工具模型可见视图

状态：已确认的实施规格  
当前实施阶段：Researcher、Intervention 与 Mechanism Distiller 影子 A/B 已完成，等待正式迁移决策  
最后更新：2026-08-13

## 1. 目的与范围

本设计只优化 Teacher Model 通过查询工具读取的模型可见内容。底层 Artifact 继续尽量
保留完整事实、Provider metadata、原始 Tool Result、完整 Model Input 和 Harness
生命周期事件；模型可见视图是从 Artifact 派生的有损投影，不是新的事实源。

当前影子代码实施范围包含：

1. Teacher Judgment 输出 `score` 与简短 `assessment`；
2. `get_evaluation_case` 默认精简视图；
3. Student Trajectory 去重、Student 有效上下文与 Extension Change 分层视图；
4. Failure Analyst 使用的 Student Capability View；
5. Hypothesis Researcher 使用的 Student Behavior Interface。
6. Intervention Worker 使用的紧凑 Editable Context 与精确 Block View。

Intervention Worker 作为第二轮影子实验实现，不改变正式 Worker 的默认查询工具。
Trial Reviewer 的影子实现已经放弃。Mechanism Distiller 已完成独立影子实现与真实 API
A/B，但尚未替换正式模板或删除正式 Trial 查询工具。

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

当前建议保留影子实现作为正式迁移候选，不在本轮直接替换生产模板。正式迁移前可单独
修正终态 Schema 对可选空字段的 Provider 展示，避免把与 Evidence View 无关的
`"null"` 重试计入角色稳定性；Hook probe 使用 Student profile 的架构边界也应作为独立
议题评估，不与 dossier 迁移绑定。
