# Mechanism Distillation Protocol

## 状态与边界

本文定义 Mechanism Distiller 的最小低冗余输出协议。该协议已经过独立字段完整性审查，并已实现为 Shadow Mechanism Distiller；正式 Evolution Controller 尚未迁移到该角色。

Distillation Result 是一次 Distillation 的控制结果。Mechanism Spec 是 Distillation 成功时产生的实现无关机制定义。两者共用一个角色输出入口，但保持独立领域语义：Result 决定 Controller 路由，Spec 约束 Prompt Researcher、Mechanism Compiler、Conformance Reviewer、Candidate Reviewer 与 Promotion Gate。

证据来源、Evidence Coverage、Teacher transcript 和 Artifact Reference 不属于运行机制正文，由程序从现有 Evidence Review、Trial Review、Control Effect 和 Role Artifact 组装为 Distillation Provenance。

## 顶层结果

```python
DistillationOutcome = Literal[
    "distilled",
    "needs_evidence",
    "not_distillable",
]

class DistillationResult:
    outcome: DistillationOutcome
    mechanism: MechanismSpec | None
    obligation: str | None
```

- `outcome`：声明 Distillation 已形成机制、仍缺少同一 Research Scheme 下的判别证据，或当前 Research Scheme 无法形成忠实机制。
- `mechanism`：只在 `outcome="distilled"` 时承载一份完整 Mechanism Spec；程序在验证并持久化后生成 Artifact Reference。
- `obligation`：只在非成功分支承载一个完整的上游义务，同时说明阻塞事实和必须补充或修改的内容。

字段互斥规则：

| `outcome` | `mechanism` | `obligation` | Controller 语义 |
| --- | --- | --- | --- |
| `distilled` | 必须存在 | 必须为空 | 进入含 `hook_model` phase 的 Prompt Research/Feasibility，或直接进入 Mechanism Compilation |
| `needs_evidence` | 必须为空 | 必须存在 | 在预算允许时返回 Trial Selection，验证一个同一冻结假设下可执行的证据缺口 |
| `not_distillable` | 必须为空 | 必须存在 | 返回 Hypothesis Researcher；是否修订 Research Scheme 或请求重新分析 Failure Direction 由 Researcher 自身协议决定 |

`obligation` 不保存一般性过程说明。`needs_evidence` 的内容必须是 Trial Selector 能够调度的判别问题；`not_distillable` 的内容必须同时指出不能忠实提炼的边界和 Researcher 需要改变的研究假设范围。

### Model submission and deterministic assembly

`DistillationResult` 是持久化产品协议，不要求 Teacher 在最终 Tool Call 中重新输出完整嵌套 Mechanism。Shadow 实现使用程序维护的临时 draft，按 effect、单个 phase、state/constraints 分片接收并即时校验。验证成功后程序返回 run-local `mechanism_ref`，Teacher 的浅层终态提交为：

```python
class DistillationSubmission:
    outcome: DistillationOutcome
    mechanism_ref: str | None
    obligation: str | None
```

程序只接受指向已验证 draft 的 `mechanism_ref`，随后确定性解析并持久化为上面的完整 `DistillationResult.mechanism`。`draft_id` 与 `mechanism_ref` 是 Harness transport state，不进入最终 Mechanism Spec，也不成为下游协议。非成功分支不创建 draft，只提交 outcome 与 obligation。

## Mechanism Spec

```python
class MechanismSpec:
    effect: EffectSpec
    phases: list[PhaseSpec]
    state: list[StateSpec]
    constraints: list[str]
```

- `effect`：声明 Candidate 最终需要证明的效果类型与可观察成功条件。
- `phases`：按 Harness Lifecycle 顺序定义一个或多个 phase-local 判断与动作；同一 phase 在一份 Mechanism 中最多出现一次。
- `state`：声明跨 phase 或跨 activation 保留的最小 rollout-local 机制状态；无状态机制使用空列表。
- `constraints`：只记录无法从 effect、phase、task、on_success、fallback、state 和 activation limit 推导出的额外实现不变量；没有额外约束时为空列表。

Mechanism Spec 不保存自然语言实现解释。每项要求必须位于拥有该要求的最窄结构中：phase-local 行为属于 Phase Spec，跨 phase 关系由有序 phase、state 写入 action 和后续 state guard 共同表达，额外不变量属于 `constraints`。

## Effect Spec

```python
EffectKind = Literal["task_outcome", "behavioral_intermediate"]

class EffectSpec:
    kind: EffectKind
    success: str
```

- `kind`：选择后续效果判据；`task_outcome` 要求可归因任务收益，`behavioral_intermediate` 要求目标中间行为出现并满足任务质量护栏。
- `success`：给出 Candidate rollout 中必须观察到的效果及其适用范围，不复述 Mechanism 的执行步骤，也不记录历史 Trial 的实际结果。

`effect.success` 是 Conformance Reviewer 与 Candidate Reviewer 的效果目标。机制如何产生该效果由 `phases` 定义。

## Phase Spec

```python
class PhaseSpec:
    phase: HookPhase
    guards: list[str]
    task: DecisionTask | GenerationTask
    on_success: str
    fallback: FallbackPolicy
    activation_limit: int
```

- `phase`：指定 Hook 获得控制权的 Harness Lifecycle Phase。
- `guards`：列出执行 task 前可由程序直接验证的结构条件；任一 guard 不成立时直接 `continue_without_change`，不调用模型、不修改 state，也不消耗 activation limit。
- `task`：定义该 phase 唯一的三值判断任务或文本生成任务及其精确输入边界。
- `on_success`：完整描述 Decision Task 为 `positive` 或 Generation Task 返回非空文本时 Harness 必须执行的 phase-local 动作，包括必要的状态更新、任务输出使用方式和固定 Student-visible 内容。
- `fallback`：定义 Decision Task 为 `negative`、`uncertain`，Generation Task 返回空或不可用文本，或 activation budget 耗尽时的行为。
- `activation_limit`：限制一个 Student rollout 中该 phase 成功执行 `on_success` 的最大次数，必须为正整数。

`on_success` 必须自包含。固定反馈文本、上下文修改目标、task output 的绑定、state 更新顺序或 Final Decision 变化不能只出现在审计材料中。

Controller 在调用 task 前检查 activation limit。预算已耗尽时不执行 task，直接使用 `fallback.exhausted`；只有 `on_success` 实际提交后才增加计数。Hook-model 传输错误或 Harness runtime error 必须作为运行错误显式暴露，不得伪装成语义 `uncertain`。

## Phase Task

```python
DecisionEvaluator = Literal["deterministic", "hook_model"]

class DecisionTask:
    kind: Literal["decision"]
    evaluator: DecisionEvaluator
    inputs: list[TaskInput]
    positive: str
    negative: str
    uncertain: str

class GenerationTask:
    kind: Literal["generation"]
    evaluator: Literal["hook_model"]
    inputs: list[TaskInput]
    output_name: str
    requirement: str
```

- `DecisionTask.kind`：固定为 `decision`，声明 task 返回 `positive`、`negative` 或 `uncertain` 控制标签。
- `DecisionTask.evaluator`：选择由确定性规则还是 Student Hook model 完成当前判断；`hook_model` 会激活 Prompt Research/Feasibility。
- `DecisionTask.inputs`：按稳定顺序声明判断所需的全部可见值和权威运行时来源；判断器不得读取未声明输入。
- `positive`：定义现有输入足以执行 `on_success` 的可观察条件。
- `negative`：定义现有输入足以确定不执行 `on_success` 的可观察条件。
- `uncertain`：定义现有输入不足、冲突或无法可靠归类时的可观察条件。
- `GenerationTask.kind`：固定为 `generation`，声明 task 返回供 `on_success` 使用的自然语言文本，而不是控制标签。
- `GenerationTask.evaluator`：固定为 `hook_model`，因为确定性文本转换应直接写入 action，不需要 Prompt Research。
- `GenerationTask.inputs`：按稳定顺序声明生成任务允许读取的全部值和权威运行时来源。
- `output_name`：提供 phase 内唯一的 task output 名称，`on_success` 必须通过该名称引用生成结果。
- `requirement`：定义生成内容应完成的语义任务、必须保留的信息和质量边界，不规定具体 Prompt wording。

Decision Task 的三项边界必须互斥并覆盖所有允许输入。三值标签属于协议常量，不在每份 Mechanism Spec 中重复声明。Hook-model 返回无法解析为三值标签时执行 `fallback.uncertain`；这不包括 provider、网络或 Harness runtime error。

Generation Task 的 runtime 接受条件是返回非空文本；语义质量由 Prompt Research/Feasibility 预先验证，并在 Candidate Conformance 中复核。空文本执行 `fallback.default`，模型调用错误作为 runtime error 暴露。

Prompt Researcher 研究所有 `evaluator="hook_model"` 的 Phase Task。它可以改变 Prompt，但不能改变 inputs、Decision Task 三项边界、Generation Task requirement、phase action、state 或 effect。

Generation Task 示例：

```json
{
  "kind": "generation",
  "evaluator": "hook_model",
  "inputs": [
    {
      "name": "当前检索结果",
      "sources": ["stage.tool_result"]
    }
  ],
  "output_name": "rewritten_result",
  "requirement": "在不增加事实的前提下，把当前检索结果概括为保留实体、关系和出处的短文本。"
}
```

对应 `on_success` 必须明确绑定输出，例如“使用 `rewritten_result` 替换当前 ToolResult 的 Student-visible content，并保留原始 metadata”。

## Task Input

```python
class TaskInput:
    name: str
    sources: list[str]
```

- `name`：给出判断任务中的稳定语义名称，例如“当前候选终答”或“已完成检索交互”。
- `sources`：按投影顺序列出构造该输入所需的受控 Hook runtime source；列表非空、无重复，程序据此选择 API 文档并限制实现访问范围。

每个 runtime source 由框架 Source Catalog 提供类型、生命周期说明和固定的模型可见 projector。Catalog 只暴露 Hook 调用期间能够读取的值；当前 phase 的临时对象使用该 phase 的 `stage.*` source。程序按 `sources` 顺序生成带 `name` 的标准输入块；Distiller 不撰写自由文本 projection。Prompt Researcher probe 与 Candidate Hook 必须调用同一 projector 并记录 input projection digest，避免 Feasibility 使用完整轨迹而 Compiler 只能访问局部输入。需要尚不存在的 source projector 时，当前 Mechanism 不可进入 Prompt Research 或 Compilation。

每个已声明 Mechanism state 自动形成受控 source `state.<name>`，使用框架固定的 state-value projector，不要求把动态 state name预注册到全局 Source Catalog。只有 `StateSpec` 中存在的名称才能形成该 source；删除或修改 State Spec 会同时改变 task 与 input projection digest。

## Fallback Policy

```python
class FallbackPolicy:
    default: str
    uncertain: str | None
    exhausted: str | None
```

- `default`：定义 Decision Task 为 `negative` 或 Generation Task 返回空或不可用文本时的行为，并作为未提供覆盖项时的公共 fallback。
- `uncertain`：只在 `uncertain` 行为不同于 `default` 时提供覆盖，否则为空。
- `exhausted`：只在 activation budget 耗尽后的行为不同于 `default` 时提供覆盖，否则为空。

公共无修改 fallback 必须使用稳定动作 `continue_without_change`，无需在三个分支重复自然语言说明。只有真实更新已声明 state 时才使用其他 imperative action。Fallback 不得执行 `on_success` 的主要效果。

## State Spec

```python
class StateSpec:
    name: str
    value_type: str
    initial: object
```

- `name`：提供 Mechanism 内唯一、可被 phase guard、action 或 flow 引用的状态名称。
- `value_type`：使用框架受控类型标识声明状态值类型，使 Compiler 能建立有类型的 rollout-local state boundary。
- `initial`：声明每次状态生命周期开始时的确定性初始值，并且必须符合 `value_type`。

Mechanism state 均以 Student rollout 为生命周期；单次 activation 临时值是实现局部变量，不进入 State Spec。受控 `value_type` 至少支持 `bool`、`int`、`str` 和 JSON-compatible object，程序验证 `initial` 类型。Phase 对 state 的读取条件写入对应 `guards` 或 task inputs，写入动作写入对应 `on_success` 或 fallback。所有 state 引用必须能解析到唯一 State Spec，未被任何 phase 使用的 state 不得声明。

## 跨 phase 表达

协议不设置独立 `cross_phase_flow` 字段。`phases` 按 Harness Lifecycle 稳定顺序排列；前序 phase 在 `on_success` 或 fallback 中写入 state，后序 phase 通过 guards 或 task inputs 读取该 state。这样跨 phase 因果关系只有一份可执行定义，不再维护一份重复的自然语言流程。

## Constraints

```python
constraints: list[str]
```

`constraints` 记录所有合法实现都必须遵守、但无法从其他结构化字段确定性推导的额外机制不变量和机制特有的强制观测要求。典型内容包括不得代替 Student 调用任务工具、不得注入未检索事实、不得把 Teacher-only 信息写入 Student context，或必须记录一个框架默认 trace 不包含的机制状态变化。

可由 `activation_limit`、fallback、Task Input 或 `on_success` 直接推出的要求不得再次写入 `constraints`。例如 `activation_limit=1` 已经表达“不得重复执行正向动作”，`fallback.uncertain="continue_without_change"` 已经表达“不确定时不得干预”。

## Hook Prompt Product

Prompt Researcher 的产物独立于 Mechanism Spec，并与一个冻结的 Hook-model Phase Task 确定性绑定：

```python
ThinkingMode = Literal["enabled", "disabled"]
ResponseAdapter = Literal["tri_label", "raw_text", "structured_edit"]

class HookPromptProduct:
    phase: HookPhase
    task_digest: str
    input_projection_digest: str
    prompt: str
    thinking_mode: ThinkingMode
    response_adapter: ResponseAdapter
```

- `phase`：标识该 Prompt 所属的唯一 Hook-model phase。
- `task_digest`：绑定冻结 Phase Task 的规范化内容，防止 Mechanism 修订后复用旧 Prompt。
- `input_projection_digest`：绑定 Source Catalog 与有序 Task Input 形成的实际模型可见投影。
- `prompt`：保存 Prompt Researcher 最终提交并通过 Feasibility 审阅的准确 Prompt 正文。
- `thinking_mode`：冻结 Probe 支持的 Student thinking mode，Compiler 不得重新选择。
- `response_adapter`：冻结运行时解释方式；Decision Task 使用 `tri_label`，Generation Task 当前使用 `raw_text`。Runtime 与 Shadow Compiler 已兼容返回数字 `block_id` 操作的 `structured_edit`，但 Prompt Researcher 尚不产生该产品。

程序为 Product 计算内容 digest、记录 Student Model Provenance，并保存全部 Prompt attempts 和 Probe Artifacts。Shadow Compiler 只看到 phase 到 Product Reference 的绑定；程序在 Candidate extension 目录物化不可读写的托管模块，并由 `HookContext.call_prompt_product` 使用冻结 projector 调用 Student。Compiler 只能消费规范化结果并落实 Mechanism 的 guard、activation limit、目标、作用域、状态、action 与 fallback；不允许读取或修改 Prompt、thinking mode、输入投影或 response adapter。

## Distillation Provenance

Distillation Provenance 由程序持久化，不由 Mechanism Distiller重新总结：

```python
class DistillationProvenance:
    source_refs: list[ArtifactReference]
    coverage_ref: ArtifactReference
    evidence_review_ref: ArtifactReference
    role_artifact_ref: ArtifactReference
    mechanism_digest: str
```

- `source_refs`：只引用支持本次 Distillation 的底层 Trial Review、Trial 和其他不可变 Evidence Artifact，不重复包含最终 Evidence Review。
- `coverage_ref`：引用 Controller 已确定性维护的正例、负例、不确定类和 distinct-example 覆盖快照，不复制相同结构。
- `evidence_review_ref`：指向授权本次 Distillation 的最终 Evidence Review。
- `role_artifact_ref`：指向保存 Distiller Model Input、工具调用、transcript 和 usage 的完整 Role Artifact。
- `mechanism_digest`：把 Provenance 与持久化后的准确 Mechanism Spec 内容绑定，防止引用漂移。

历史 Trial 结果、Evidence Coverage、Teacher 推理摘要、已知证据限制和 provider metadata 均通过这些引用查询，不复制进 Mechanism Spec。若某项限制会改变可执行边界，Distiller 必须把它落实到 `effect.success`、Phase Task、fallback 或 `constraints`；无法落实时返回 `needs_evidence` 或 `not_distillable`。

## 全局验证规则

- `effect.kind` 必须显式填写，不提供默认 Promotion 目标。
- `phases` 至少包含一项、phase 不重复，并按 Harness Lifecycle 的稳定顺序排列。
- 每个 phase 只有一个 task；Decision Task 和 Generation Task 由 `kind` 严格区分，拒绝另一分支的字段。
- 每个 task 内 `TaskInput.name` 唯一；`sources` 非空、无重复，并且全部存在于受控 Source Catalog。
- Decision Task 的 positive、negative、uncertain 边界必须互斥且覆盖允许输入。
- Generation Task 的 `output_name` 必须在本 phase 唯一，并且 `on_success` 必须引用该名称。
- 任一 guard 不成立时不执行 task、不写 state、不消耗 activation limit，直接 `continue_without_change`。
- `fallback.uncertain=None` 和 `fallback.exhausted=None` 表示继承 `default`，不表示缺少 fallback。
- `activation_limit` 是 phase × Student rollout 作用域的正整数，只在 `on_success` 实际提交后计数。
- state name 唯一，`initial` 符合受控 `value_type`；所有 state 引用必须可解析，未被任何 phase 使用的 state 不得声明。
- `constraints` 不得复述 effect、guard、Task Input、task boundary、action、fallback、state 或 activation limit 已经确定的要求。
- 每个 Hook-model task 必须具有 task/input digest 完全匹配且通过 Feasibility 的 Hook Prompt Product，才能进入 Mechanism Compilation。
- Distillation Provenance 必须通过 `mechanism_digest` 与准确 Mechanism Artifact 绑定。

## 完整成功示例

```json
{
  "outcome": "distilled",
  "mechanism": {
    "effect": {
      "kind": "behavioral_intermediate",
      "success": "Student 在复杂回答前获得一份不含答案事实的分步计划；如果首次终答遗漏计划中的必要步骤，机制至多推迟一次并要求按原计划补全。"
    },
    "phases": [
      {
        "phase": "post_prompt",
        "guards": [
          "rollout state plan 为空字符串。"
        ],
        "task": {
          "kind": "generation",
          "evaluator": "hook_model",
          "inputs": [
            {
              "name": "当前任务",
              "sources": ["core.question"]
            }
          ],
          "output_name": "generated_plan",
          "requirement": "生成只描述解题步骤和检查项、不包含候选答案或外部事实的简短计划。"
        },
        "on_success": "把 generated_plan 原样保存到 rollout state plan，并追加 Student-visible system message 'Follow this plan before answering:\n{generated_plan}'。",
        "fallback": {
          "default": "continue_without_change",
          "uncertain": null,
          "exhausted": null
        },
        "activation_limit": 1
      },
      {
        "phase": "pre_final",
        "guards": [
          "rollout state plan 为非空字符串。"
        ],
        "task": {
          "kind": "decision",
          "evaluator": "hook_model",
          "inputs": [
            {
              "name": "已注入计划",
              "sources": ["state.plan"]
            },
            {
              "name": "当前终答候选",
              "sources": ["stage.final_decision"]
            }
          ],
          "positive": "当前终答候选明显遗漏计划中至少一个回答任务所必需的步骤或检查项。",
          "negative": "当前终答候选已经完成计划中与回答任务有关的必要步骤和检查项。",
          "uncertain": "无法从计划与当前终答候选可靠判断必要步骤是否完成。"
        },
        "on_success": "将当前终答改为 defer，追加准确的 Student-visible user message 'Revise the answer once by completing the missing required steps from the existing plan. Do not replace the plan or introduce unsupported facts.'，并请求下一次生成。",
        "fallback": {
          "default": "continue_without_change",
          "uncertain": null,
          "exhausted": null
        },
        "activation_limit": 1
      }
    ],
    "state": [
      {
        "name": "plan",
        "value_type": "str",
        "initial": ""
      }
    ],
    "constraints": [
      "机制不得替换 Student 自己产生的工具调用或工具结果。"
    ]
  },
  "obligation": null
}
```

## 非成功示例

```json
{
  "outcome": "needs_evidence",
  "mechanism": null,
  "obligation": "补充一个已覆盖双实体且应保持不干预的独立 Trial，以区分单侧检索 predicate 与仅仅出现双实体问题。"
}
```

```json
{
  "outcome": "not_distillable",
  "mechanism": null,
  "obligation": "现有 Intervention 的成功依赖 Teacher-only 世界知识，无法从任何允许的 Hook runtime input 重现；Researcher 必须改写语义任务，使触发边界只依赖 Student-visible evidence。"
}
```

## 消费关系

- Evolution Controller 只消费 `outcome`、`mechanism` 是否存在和 `obligation`。
- Prompt Researcher 只消费 `evaluator="hook_model"` 的 phase、Phase Task 和实际 Task Input 投影，并提交该冻结任务的 Hook Prompt Product。
- Shadow Compiler 消费完整 Mechanism Spec 和 phase 到 Prompt Product Reference 的绑定；程序根据 Task Input sources 选择完整 API 文档。Compiler 不重新解释三值边界、生成要求或 effect，也不重新构造 Hook-model 输入和 Prompt。
- Shadow Conformance Reviewer 消费 effect、phase、task、on_success、fallback、state 和 constraints，并在原 Trial Example 的真实 Candidate rollout 上判断实现保真与局部目标行为。正确投影下的 managed Prompt Product 语义错判返回 evidence，不要求 Compiler 修改冻结 Prompt。
- Candidate Reviewer 与 Promotion Gate 消费 `effect.kind` 和 `effect.success`，结合全量 Candidate Evaluation、Conformance 与成本证据判断是否晋升。
- Experience Summarizer 从 Distillation Provenance 和后续 Feasibility、Conformance、Candidate 结果形成经验，不把 Mechanism Spec 当作观察事实来源。
