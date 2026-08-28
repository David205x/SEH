# Experience Summarizer 重构设计

本文记录已确认的 Experience Summarizer 重构方案，以及为其提供稳定来源、身份和路由所需的角色协议与确定性机制修改。统一术语以 [CONTEXT.md](../../CONTEXT.md) 为准。

## 1. 目标与范围

Experience Summarizer 是基于规范化 Evidence 形成 Experience Draft 的 Teacher 能力。它不从完整 Artifact 重新发现失败模式，不重新执行工作流根因分析，不设计 Intervention、Mechanism 或 Prompt，也不负责 Experience Store 的确认、合并与持久化。

本轮将其拆为两个独立 Role Run：

- **Capability Summarization Pass**：判断 Evidence 是否足以形成 Student Capability Experience Draft。
- **Direction Summarization Pass**：判断 Evidence 是否足以形成 Experiment Direction Experience Draft。

两个 Pass 可以共享同一来源 Evidence，但使用各自的 Packet 投影、Prompt、工具和输出协议，不读取对方的 Draft。Teacher Work 使用后续独立路径，不进入这两个 Pass。

当前交付边界止于 Experience Draft Artifact。Draft Settlement、Research Experience 确认和 Experience Store 属于后续设计。

## 2. 总体数据流

```text
typed workflow result
    ↓
source-specific trigger selection
    ↓
source adapter + detail projector
    ↓
Experience Observation Packet
    ├── Capability projection → Capability Summarization Pass
    └── Direction projection  → Direction Summarization Pass
                                  ↓
                         Experience Draft Artifact
```

Source Adapter 只从当前 Work Item、Control Journal 和已附着 Artifact 中直接投影事实或确定性派生关系。无法建立的内容标记为 `unknown` 或 `not_applicable`，不生成补充性自由文本。

## 3. Experience Observation Packet

### 3.1 模型可见结构

Packet 的公共模型视图包含：

```yaml
observations:
  - observation_id: 1
    subject: ...
    expected: ...
    observed: ...
    comparison: ...
    conditions: ...
    validity: ...
    evidence_structure: ...
    open_checks: ...

detail_directory:
  - detail_id: 1
    observation_id: 1
    resolves: input_validity
    coverage: complete
    description: ...
```

| 字段 | 职责 |
|---|---|
| `observation_id` | 为当前 Packet 内的一条 Observation 提供短数字引用，供 Draft 绑定 Evidence。 |
| `subject` | 说明本条 Observation 直接观察的 Student、Hook-model、研究方案或机制效果。 |
| `expected` | 保存来源 Artifact 已声明的有效预期、reference label 或 expected effect。 |
| `observed` | 保存实际模型决策、Trial 结果、Candidate 效果或门禁结果。 |
| `comparison` | 保存已存在的处理组/对照组、Incumbent/Candidate、同输入或配对比较；不由程序推断语义等价。 |
| `conditions` | 保存 thinking mode、Hook phase、输入形态和其他决定结论边界的运行条件。 |
| `validity` | 分别记录 reference、模型输入、实现忠实性和数据环境等边界的 `confirmed`、`failed`、`unknown` 或 `not_applicable` 状态。 |
| `evidence_structure` | 保存重复次数、不同 Example、matched control、配对关系和计数，不生成 Support Verdict。 |
| `open_checks` | 列出可能改变 Draft eligibility、且有授权 Detail 可以解决的未知条件。 |
| `detail_directory` | 提供按需 Detail 的数字入口、作用、覆盖范围和一句话内容说明。 |

Capability Observation 额外包含程序从来源 Artifact 原样提取的冻结 predicate 或明确标注的规则正文，作为 `decision_scope`；Adapter 只可移除同字段内的内部路径前缀，不再把 phase、decision inputs 和 predicate 重新拼写成新句子，该字段也不由 Summarizer 生成。Hook Feasibility 按真实 prefix case 展开 Observation，`expected` 默认直接包含对应 `decisive_observation`，`observed` 保存逐 thinking mode 的重复 raw label。

每条 Observation 必须具有 `expected` 和 `observed`。缺少任一项时，不创建该 Observation。

Direction projection 额外提供程序维护的 `direction_context`；Capability projection 不接收 Capability 分类，也不要求模型生成被测任务名称或运行条件。

### 3.2 来源语义

控制器事件名和内部阶段状态不直接进入 Packet。Prompt Assembly 根据本次实际 Control Journal 与 Artifact，动态加入一段 Source Processing Context，说明：

- 本次已经完成的测试、Review 和 Gate；
- 每个结果在其职责范围内证明了什么；
- 当前来源没有建立哪些证据边界。

只注入本次来源的说明，不在固定 System Prompt 中罗列全部工作流阶段。

### 3.3 程序内部信息

Packet 不重复保存 `packet_id`、独立 `schema_version`、`model_identity`、`harness_version` 或来源 digest。外层 Teacher Role Artifact 已保存 schema、Model Input digest 和 resource artifacts。

程序在资源注册表中维护：

- Observation 到来源 Artifact 字段的映射；
- Detail 到来源 Artifact 投影的映射；
- Research Direction 三层身份与具体 revision；
- 本次 Role Run 实际读取的 Detail。

## 4. Experience Detail

### 4.1 工具

两个 Pass 共用一个只读工具：

```python
inspect_experience_detail(detail_id: int) -> str
```

`detail_id` 是 Packet 目录提供的数字编号。工具只读取一个已授权、能够解决已声明未知条件的有界投影。

### 4.2 Detail Directory

| 字段 | 职责 |
|---|---|
| `detail_id` | 为一次工具调用提供稳定数字参数。 |
| `observation_id` | 绑定该 Detail 所属的 Observation。 |
| `resolves` | 指明该 Detail 可以解决的 eligibility 条件。 |
| `coverage` | 使用 `complete` 或 `bounded_projection` 说明内容覆盖程度。 |
| `description` | 用一句话说明调用后会看到的内容。 |

### 4.3 内容生产

Detail 由来源专用 Detail Projector 从已有 Artifact 确定性生成。Projector 可以复制类型化字段、计算配对与重复关系、使用固定模板排版并复用已有轨迹投影，不调用额外模型进行二次总结。

工具结果使用统一短头部，正文采用与内容匹配的格式：

```text
Detail 1
Observation: 2
Resolves: input_validity
Coverage: complete

<detail-specific projection>
```

模型输入使用消息边界，重复决策与指标比较使用紧凑表格，轨迹内容使用职责对应的既有投影。

Detail 不暴露 Artifact 路径、digest、JSON Pointer、Run metadata、隐藏 reasoning 或无关工作流历史。同一 `detail_id` 最多读取一次；不设置固定 Detail 总读取数量上限，调用受 Role 自身的 turn/token 预算约束。

来源天然无法提供某项硬条件，且所有候选 Observation 都无法成立时，Source Adapter 返回 `None`，不调用对应 Pass。运行本应产生的 Artifact 缺失或损坏时，Source Adapter 报告数据完整性错误。

## 5. Capability Summarization Pass

### 5.1 职责

Capability Pass 只判断规范化 Observation 是否支持冻结 Student 或 Hook model 的一个狭窄行为边界。它不提出研究处置、修复策略、Prompt 修改或 Mechanism 方案。

Capability Proposal 必须同时满足：

1. expected 与 observed 针对同一狭窄语义操作；
2. reference 或 expected behavior 有效；
3. 实际模型可见输入有效且完整；
4. 实现、投影与解析忠实；
5. 数据或环境没有提供更直接的解释；
6. Evidence Structure 满足以下至少一种：
   - 同一有效输入重复产生一致偏差；
   - 同一有效条件下发生实质性决策翻转；
   - 至少两个语义等价的有效输入产生相同偏差。

单次未复现异常只保留为 Observation。

Capability 不使用受控 Capability catalog。程序提供不同 Example 的决定性语义与重复结构，是否支持同一个 `observed_limitation` 由 Capability Pass 判断。

### 5.2 触发来源

| Experience Trigger Event | 激活方式 |
|---|---|
| `hook_feasibility.needs_research_revision` | 直接激活；Probe 恒定提供真实输入、thinking mode、重复调用和 expected/observed label。 |
| `evidence_reviewer.reject` | 当 Trial Evidence 存在同输入重复或至少两个可能可比 Example 时激活。 |
| `evidence_reviewer.revise` | 与 reject 使用相同的来源级结构判断。 |
| `conformance.revise` | 仅在 Findings 包含非 parse-error 的 evaluator mismatch，且具有重复或可比较直接模型决策时激活。 |

其他现有负向触发不提供直接且可归因的模型行为，不激活 Capability Pass。

### 5.3 输出协议

```python
class CapabilityExperienceProposal:
    observed_limitation: str
    evidence_refs: list[int]


class CapabilityExperienceSummary:
    items: list[CapabilityExperienceProposal]
```

| 字段 | 职责 | 建议目标 | 硬上限 |
|---|---|---:|---:|
| `observed_limitation` | 描述模型不能稳定完成的具体语义区分；不得只复述 label、phase 或 evaluator 类型。 | 420 | 600 |
| `evidence_refs` | 引用当前 Packet 中直接支持该 Proposal 的 Observation 数字编号。 | — | — |

`items` 允许为空，不设置任意数量硬上限。Prompt 要求提交能够独立成立的最小集合；程序拒绝完全重复的 `observed_limitation + evidence_refs`，并要求一条 Proposal 的所有 refs 共享同一 Decision Scope。

模型不输出 Decision Scope、运行条件摘要、Capability 分类、Evidence 计数、confidence 或研究建议。`observed_limitation` 必须明确写出被观察对象（`Hook model` 或 `Student`），但不得复述完整 predicate；对于误触发负例，优先写成“无法稳定排除明确不应触发的输入：具体类别”。程序把 Proposal 物化为独立 Capability Experience Product：每项包含来源 Artifact 的原始 `decision_scope`、`observed_limitation`、由结构化 expected/observed decision 聚合的紧凑 `evidence_summary`，以及解析后的稳定 `evidence_refs`。Role Artifact 保留原始模型 Proposal；Product Artifact 尚未经过 Experience Store Settlement 或跨 Attempt 合并。

## 6. Research Direction 与 Direction Summarization Pass

### 6.1 三层谱系

Research Direction 是以下程序维护路径：

```text
Failure Direction
└── Research Scheme
    └── Mechanism Scheme
        ├── Candidate Attempt
        └── Candidate Attempt
```

Direction Context 使用：

```yaml
direction_context:
  failure_direction:
    ref: ...
    summary: ...
  research_scheme:
    ref: ...
    summary: ...
  mechanism_scheme:
    ref: ...
    summary: ...
  update_target: mechanism_scheme
```

| 字段 | 职责 |
|---|---|
| `failure_direction` | 绑定 Failure Analyst 识别的问题模式，使平行 Research Scheme 可以按同一失败模式聚合。 |
| `research_scheme` | 绑定 Researcher 提出的因果研究方案及其 revision。 |
| `mechanism_scheme` | 绑定 Distiller 提炼的实现无关机制及其 revision；Distillation 前为 `null`。 |
| `update_target` | 指明本次 Evidence 直接更新三层中的哪一层，由触发来源确定。 |

三层 `summary` 均由程序从首次或当前有效类型化产物固定投影；模型不生成合并键或方向描述。

### 6.2 身份与 revision

- Failure Analyst 每次成功提交创建新的 `failure_direction_id`。
- Hypothesis Researcher 首次提交方案时创建 `research_scheme_id`。
- 对当前方案补充描述或保留核心因果方案的修订，保留 `research_scheme_id` 并增加 revision。
- Researcher 更换核心因果方案时，在同一 Failure Direction 下创建新的 `research_scheme_id`。
- 首次成功 Distillation 创建 `mechanism_scheme_id`。
- Hook Feasibility、Compiler 或 Conformance 产生的 Mechanism Spec 修订保留 `mechanism_scheme_id` 并增加 revision。
- 所有历史 Hypothesis 与 MechanismSpec Artifact 保留；current pointer 只指向最新 revision。

Researcher 处理 continuation 时提交：

```python
scheme_action: Literal[
    "revise_current",
    "start_new",
    "reanalyse_failure",
]
```

| 值 | 职责 |
|---|---|
| `revise_current` | 保留当前 Research Scheme 身份并创建新 revision。 |
| `start_new` | 保留 Failure Direction，创建新的平行 Research Scheme。 |
| `reanalyse_failure` | 不继续当前 Research Scheme，路由 Failure Analyst 建立新的 Failure Direction。 |

Controller 生成和继承 ID，Researcher 不填写 ID。

### 6.3 路由修改

研究层下游回流先进入 Hypothesis Researcher。Candidate rejection 不再直接调用 Failure Analyst；Researcher 根据 Evidence 与历史 Direction Draft 选择修订当前方案、开始平行方案或请求重新分析 Failure Direction。只有 `reanalyse_failure` 路由 Failure Analyst。

### 6.4 Direction 触发与更新层级

| Experience Trigger Event | `update_target` |
|---|---|
| `evidence_reviewer.reject` | `research_scheme` |
| `evidence_reviewer.revise` | `research_scheme` |
| `mechanism_distiller.not_distillable` | `research_scheme` |
| `hook_feasibility.needs_spec_revision` | `mechanism_scheme` |
| `hook_feasibility.needs_research_revision` | `research_scheme` |
| `compiler.needs_mechanism_revision` | `mechanism_scheme` |
| `compiler.implementation_blocked` | `mechanism_scheme` |
| `conformance.revise_evidence` | `research_scheme` |
| `conformance.revise_mechanism` | `mechanism_scheme` |
| `candidate_reviewer.revise_evidence` | `research_scheme` |
| `candidate_reviewer.revise_mechanism` | `mechanism_scheme` |
| `candidate_reviewer.reject` | `mechanism_scheme` |
| `promotion_gate.failed` | `mechanism_scheme` |
| `promotion_gate.passed` | `mechanism_scheme` |

`conformance.revise_*` 与 `candidate_reviewer.revise_*` 是程序根据既有 typed route 字段派生的 Experience Trigger Event，不要求原角色输出新的自由文本。

Candidate Validation failure、unchanged rejected Candidate、Conformance implementation revision 和 Candidate Reviewer implementation revision 不激活 Direction Pass。

同一次 Candidate 只生成一个末端 Direction 事件：Reviewer `reject` 使用 `candidate_reviewer.reject`；Reviewer `accept` 后由确定性 Gate 生成 `promotion_gate.passed` 或 `promotion_gate.failed`。Reviewer revise 使用与 revision target 对应的事件。

### 6.5 Direction 证据门槛

Direction Pass 判断 Evidence 是否对 `update_target` 产生可复用更新。一个有效的决定性反例、matched control、不可操作性证据、Candidate 效果结果或完整通过的 Promotion Gate 可以支持不超出其范围的 Draft。

普通证据不足、预算耗尽、Provider failure 或没有可复用解除条件的 inconclusive 结果返回空列表。Capability 与 Direction 可以引用相同 Observation，但 Direction 必须额外说明 Evidence 对 Research Direction 的处置价值。

### 6.6 输出协议

```python
class DirectionDraft:
    evidence_update: str
    disposition: str
    revisit_condition: str
    applicability: str
    evidence_refs: list[int]


class DirectionSummary:
    items: list[DirectionDraft]
```

| 字段 | 职责 | 建议目标 | 硬上限 |
|---|---|---:|---:|
| `evidence_update` | 说明决定性 Evidence 如何改变 `update_target` 的可信程度或适用范围。 | 400 | 800 |
| `disposition` | 使用简短自然语言说明当前应如何对待 `update_target`；它不是 Controller 命令。 | 200 | 400 |
| `revisit_condition` | 说明什么具体新 Evidence 或条件变化可以改变当前 disposition。 | 240 | 500 |
| `applicability` | 限定本条 Evidence Update 成立的问题、机制、数据或运行范围。 | 200 | 400 |
| `evidence_refs` | 引用当前 Packet 中直接支持该 Draft 的 Observation 数字编号。 | — | — |

Direction Packet 只绑定一个 Research Direction 和一个 `update_target`，因此 `items` 只能为零或一条。`disposition` 不使用枚举；消费者将其视为 Evidence-bounded research update，而不是自动路由。

程序在 Draft Artifact 中附加 `experience_type`、完整 `direction_context`、`source_event`、Evidence Structure 和 provenance。模型输出的局部 Observation 编号在持久化时解析为 Packet 与来源 Artifact 下的稳定 Evidence 引用。

## 7. 涉及角色的修改

### Failure Analyst

- 每次成功提交建立新的 Failure Direction 身份。
- 由 Researcher 的 `reanalyse_failure` 激活，不再承担每次 Candidate rejection 后的默认方案重试入口。
- 输入保留当前问题 Evidence 和既有 Failure Direction 摘要，供其避免重复选择。

### Hypothesis Researcher

- 管理 Research Scheme 的语义延续关系，不管理具体 ID。
- continuation 输出增加 `scheme_action`。
- 可以修订当前方案、创建同一 Failure Direction 下的平行方案，或请求 Failure Analyst 重新分析。
- 消费 Direction 与 Capability Draft 的正式接入在 Draft Settlement 设计完成后进行。

### Evidence Reviewer

- `reject` 和 `revise` 同时是 Capability 的条件来源和 Direction 的直接来源。
- 既有 Trial Review、Coverage Summary 与 typed decision 作为 Packet 来源，不新增自由文本摘要职责。

### Mechanism Distiller

- 成功 Distillation 创建或修订 Mechanism Scheme。
- `not_distillable` 形成 Research Scheme 级 Direction 机会。
- Mechanism Spec revision 保留 Mechanism Scheme 身份和历史版本。

### Hook Feasibility Reviewer

- `needs_research_revision` 直接提供 Capability 与 Research Scheme Direction 机会。
- `needs_spec_revision` 只更新 Mechanism Scheme Direction，不形成 Capability。
- Probe Artifact 继续保存真实 Hook-model input、thinking mode、repetition、expected/observed label 和原始输出。

### Mechanism Compiler

- `needs_mechanism_revision` 与 `implementation_blocked` 提供 Mechanism Scheme Direction 机会。
- Compiler output 不作为 Student Capability 来源。
- Candidate 与 Compiler revision 关联当前 Mechanism Scheme 和具体 MechanismSpec revision。

### Conformance Reviewer

- typed route `evidence` 与 `mechanism` 分别派生 Research Scheme 和 Mechanism Scheme Direction 事件。
- 只有重复的直接 evaluator mismatch 可以成为 Capability 来源。
- implementation route 不触发 Capability 或 Direction。

### Candidate Reviewer 与 Promotion Gate

- Candidate Reviewer 的 evidence/mechanism revision 分别更新 Research Scheme 与 Mechanism Scheme。
- Reviewer reject 更新当前 Mechanism Scheme。
- Reviewer accept 后由 Promotion Gate 唯一生成 passed 或 failed Direction 事件。
- Candidate effect、paired changes、Hook activity、cost 和确定性 Gate 结果作为 Direction Packet 来源，不从聚合变化推断 Capability。

## 8. 确定性机制修改

### Trigger Dispatch

用独立的 Capability 与 Direction trigger 集合替代旧的统一 `ExperienceSummaryTrigger`。混合 route 由现有 typed target 派生为明确的内部 Experience Trigger Event。

### ID 与 Revision

Controller 创建并继承 Failure Direction、Research Scheme 与 Mechanism Scheme 身份，保存 revision 与当前指针。旧 Artifact 不覆盖。

### Packet Assembly

每个 Trigger family 使用独立 Source Adapter。Adapter 验证所需 Artifact、生成 Observation、建立 Detail Registry，并在无法满足最低结构时返回 `None`。

### Prompt Assembly

固定 Capability/Direction Prompt 与本次来源专用 Source Processing Context 组合。不同触发已完成的测试与 outcome 语义由动态部分解释。

### Output Validation

程序验证 Observation 引用存在且唯一、Direction 只有一个 item、Capability 不包含完全重复项，并把局部 Evidence refs 解析为可追溯来源。

### Role Execution

Capability 与 Direction 使用独立 Role Run、Prompt、预算、重试和 Artifact。两个 Pass 可以并行；一个 Pass 的失败不删除另一个 Pass 已成功形成的 Draft。

## 9. 已替换的旧边界

- 组合式 `experience_summarizer@3` 及 Teacher Work 输出已由两个独立 Pass 替换。
- 固定 `decision_scope`、四类 `capability_area` 和模型回填 `elicitation_scope` 已删除。
- 调用方传入自由文本 direction/attempt/evidence 的 builder 已由 Trigger-specific Source Adapter 替换。
- 三参数 `inspect_experience_evidence` 已由整数 `detail_id` 工具替换。
- 每次最多返回三项 Detail 的限制已删除；同一 Detail 仍禁止重复读取。
- Candidate rejection 已改为 Researcher-first 回流，并使用三层 Direction 身份。
- Conformance 与 Candidate 的 Experience event 由 typed route 确定性派生。
- architecture/reference 已同步到新角色与 Artifact 形态。

## 10. 实施与验证顺序

1. 增加三层身份、revision 和 Researcher `scheme_action`，修正研究层回流路由。
2. 拆分 Capability/Direction contract、Trigger 与 Role Run。
3. 实现 Source Adapter、Packet、Detail Registry 与单一 Detail 工具。
4. 撰写两份固定 Prompt 和各 Trigger family 的 Source Processing Context。
5. 用现有 Artifact 执行无 Student 调用的 shadow packet/role 验证。
6. 对同一输入并行执行三次真实 Teacher API 验证；结果分歧明显时扩展到五次。
7. 检查 Draft 准确性、原子性、Evidence 引用、Detail 使用和 token 成本。
8. 验证通过后替换旧 Experience Summarizer 路径，并同步 architecture/reference 文档。

本轮验证只保存 Experience Draft Artifact，不接入正式 Experience Store。
