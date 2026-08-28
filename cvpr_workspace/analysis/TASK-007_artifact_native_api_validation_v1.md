# TASK-007 Artifact-native 真实 API 验证报告 v1

## 1. 验证对象

本轮验证检查 `experience_summarizer@2` 是否能够从真实历史 Artifact 的原始字段中完成三类经验归因。模型可见的 `direction`、`attempt`、`evidence.outcome`、`evidence.comparison` 和 evidence view 内容均由 `copy_text`、`copy_json` 或固定标签的 `join_values` 构造；case 配置不再保存这些字段的人工业务总结。

程序侧仍确定性提供 trigger、source classification、实际 next work、causal neighbors、boundary kind/status 与授权 ref/view/selector。每个 Run 单独保存实际五字段输入和逐字段 Artifact 路径、JSON pointer、提取操作、原始复制值。

这些 Run 属于 TASK-007 开发期角色验证，不是 H3 Claim 或 Goal 正式证据。

## 2. 离线检查

- 18 个历史 case 均能从 Artifact 原字段完成构造。
- 150 条投影记录均包含目标字段、Artifact 相对路径、JSON pointer、操作和原始复制值。
- case schema 不再含手写 `direction`、`attempt`、`evidence`、`evidence_views` 或 `source_artifacts` 业务输入。
- 未投影 transcript、raw reasoning、tool calls、resource config、usage、hash 或 digest。
- 输入构造不调用 LLM，不使用自由文本 fallback，也不静默截断。
- 20 次工具 hard fuse、五字段输入合同、三类输出顺序、证据引用和条件化 Capability 事实句检查通过。
- 最终 233 个 Evolution 回归测试通过。

## 3. 首轮 28-run 结果与暴露问题

`task_007_attribution_validation_v6` 的 28 个真实 API Run 全部完成，无运行级失败；28/28 通过 Capability 事实句形态和输入 provenance 检查。该批次暴露三项输入/审计问题：

1. Candidate overlap 的初始 observation 只含原始 `reject`，详细的两类负例误激活只在工具视图中；一次未调用工具的 Run 因而漏掉 Capability。
2. empty-passage case 用 Mechanism goal 模拟 `role_input_sufficiency`，没有绑定 Compiler 当时真实可见的输入；Summarizer 据此保守输出空列表。
3. 三个 Run 分多次读取同一 ref/view 的不同 selector，违反当前一次合并读取的工具质量规则。

Distiller 的 3/3 输出均包含 `Student Capability + Experiment Direction`。两条经验分别描述生产 Hook evaluator 的能力边界，以及该机制不能按当前方向完成 distillation 的研究处置；结论对象和消费行为独立，因此将 rubric 从 Capability-only 修正为两类并存。

## 4. 修正与定向复核

修正均使用现有 Artifact 原文：

- Candidate Review 的初始 `outcome` 改为原始 `observed_effect`；Hook overlap 的 `comparison` 进一步使用原始 `reason`，不再只给 `reject`。
- empty-passage 的 `role_input_sufficiency` 改为绑定实际 Compiler Role Artifact 的 `input.mechanism.phase_rules`。
- Prompt 明确：同一 view 需要多个 selector 时必须一次合并请求。
- `Student Capability.lesson` 的输出合同要求 `Under X, the Student model cannot reliably Y`，并拒绝研究动作、guard、recheck、release、cost 或 utility；`applicability` 只限定观察范围。

15-run 定向复核 `task_007_attribution_validation_v7` 全部完成，无运行失败；Capability 形态、provenance、Teacher subject 和工具协议均 15/15 通过。empty-passage 3/3 稳定生成 `compiler` Teacher Work；Hook capability-only 3/3 稳定；Distiller 3/3 稳定生成 Capability+Direction；三个 Direction-only control 均未误产 Capability。Hook overlap 为 2/3 两类齐全，剩余一次只产 Direction。

在 Hook overlap 初始 comparison 加入 Candidate Reviewer 原始 `reason` 后，最终 3-run `task_007_attribution_validation_v8_overlap_final` 达到：

- 3/3 completed，0 failed；
- 3/3 exact type 为 `student_capability + experiment_direction`；
- 3/3 Capability 为条件化 Student 模型事实句；
- 3/3 input provenance 完整；
- 3/3 Teacher subject 与工具协议通过；
- 每次仅调用一次 evidence tool，无重复 view。

## 5. 归因质量结论

### 5.1 Student Capability

最终 Capability 输出已经收敛为可直接消费的模型边界：

- 主体始终是 `the Student model` 或 `the Student model when used as the Hook evaluator`；
- 条件限定在真实 probe/contract/input/thinking mode 或 pre-final prefix；
- 能力边界只描述模型无法稳定完成的 narrow classification/decision；
- 不再把 deterministic guard、修复动作或 recheck 当作模型能力已恢复；
- overlap 输出不再把 accuracy、token cost 或无正向效用写入 Capability，这些内容只进入 Direction。

三个代表边界稳定出现：

1. 在三标签 pre-final contract 下，Student Hook evaluator 无法稳定把 single-entity 与 both-entity 显式负例判为 negative。
2. 在 query-target verification 中，Student Hook evaluator 无法稳定识别 query 是否同时命名两个实体。
3. 在 explicit-link / no-commitment 边界上，Student Hook evaluator 无法稳定执行 negative/pass-through 分类。

### 5.2 Experiment Direction

Direction-only control 保持克制，没有把 implementation defect、单次误激活或无 differential effect 升格为 Student Capability。Direction 输出使用原始 matched-control、activation attribution、regression、selectivity 与 cost 事实，给出 stop/narrow/revisit 条件。

Capability+Direction overlap 中，两条经验使用不同结论对象：Capability 描述 Student evaluator 的条件化分类边界；Direction 处置当前 one-shot deferral 机制的实测 utility/selectivity/cost。二者没有互相复述。

### 5.3 Teacher Work

当 Compiler 当时真实可见的 Mechanism phase rules 被程序确认后，empty-passage case 3/3 归因给 `compiler`，并准确指出实际 retrieved passages 未投影到 classifier 输入。没有把该实现缺陷写成 Student Capability。

## 6. 结论边界

TASK-007 v14 的实现目标已完成：Artifact 原文投影、逐字段审计、纯 Capability 事实句合同、真实 API 归因复核与回归验证均已形成稳定产物。结果支持“Summarizer 能在这些开发期真实历史 Artifact case 上提取 consumer-ready Draft”，不支持 H3 对跨 generation 复发、方向重走、yield、false pruning 或 held-out utility 的正式主张。

TASK-007 当前应保持 `executed`，待用户审阅本报告和原始输出后决定是否标记 `accepted`。
