# Teacher 多角色 v2 代码审核手册

## 0. 范围、口径与公共运行时

本文忠实描述 `search_harness.evolution.control` 正式 Controller 当前接入的 9 个 Teacher 协议角色：

1. `failure_analyst`
2. `hypothesis_researcher`
3. `intervention_worker`
4. `trial_reviewer`
5. `evidence_reviewer`
6. `mechanism_distiller`
7. `compiler`
8. `conformance_reviewer`
9. `candidate_reviewer`

本文把 `SELECT_TRIAL`、`STAGE_CANDIDATE`、`EVALUATE_*`、`PROMOTE_CANDIDATE`、`REJECT_CANDIDATE` 视为确定性机制而不是模型角色。路由条件均按 `transitions.py` 中实际读取的变量和值描述，不用提示词中的语义判断替代程序条件。

协议代码块保留源字段声明，并为每个字段补充一行中文职责注释；为避免把“字段声明”与“验证方法”混在一起，Pydantic validator 的效果统一写入各章“输出协议/后处理”或“额外机制”。

工具代码块使用“模型可见 schema 等价签名”：保留 Python type hint，并把源码 `Annotated[..., ToolArg(choices=...)]` 的 choices 投影为 `Literal[...]`，以便直接看出允许值；minimum/maximum 和参数语义在紧邻说明中列出。它不是对内部闭包 `invoke()` 源文本的逐字符复制。

```mermaid
flowchart T
    EI["确定性 incumbent evaluation"] --> FA["Failure Analyst"]
    FA --> HR["Hypothesis Researcher"]
    HR --> ST["确定性 Trial Selector"]
    ST --> IW["Intervention Worker"]
    IW --> TR["Trial Reviewer（逐 trial）"]
    TR --> ER["Evidence Reviewer（跨 trial）"]
    ER --> ST
    ER --> HR
    ER --> MD["Mechanism Distiller"]
    MD --> ST
    MD --> C["Compiler"]
    C --> MD
    C --> SV["确定性 Stage / Validation"]
    SV --> C
    SV --> CR["Conformance Reviewer（逐 replay）"]
    CR --> C
    CR --> EC["确定性 Candidate Evaluation"]
    EC --> CAR["Candidate Reviewer"]
    CAR --> ST
    CAR --> MD
    CAR --> C
    CAR --> PG["确定性 Promotion Gate"]
    PG --> PV["Promote / Version Store"]
```



### 0.1 公共提示词组装流程

除 `intervention_worker` 外，其余角色共用 `NativeChatTeacherRuntime`：

1. 从角色目录的 `harness.json` 读取角色协议版本、输出协议版本、prompt 组件和显式工具。
2. prompt 插件通过 `load_prompt_spec()` 读取 UTF-8 `templates/system.md` 与 `templates/user.md`。
3. `role_input` 先经角色 `input_type.model_validate()` 严格校验，未知字段被拒绝。
4. `TeacherResources.bind_role_input()` 根据已验证输入冻结证据范围、trial 引用、phase 顺序或 Compiler capability packet。
5. `TeacherResources.model_context(role_id)` 生成程序维护的紧凑资源上下文。
6. `TeacherPromptSpec.render_input()` 将用户模板中的 `{{role_input}}` 和 `{{resource_context}}` 替换为 `ensure_ascii=False, indent=2` 的 JSON；系统模板原样成为首条 system message。
7. 使用 `TEACHER_*` 模型配置进入 provider-native tool loop；`parallel_tool_calls=False`。
8. 运行时为角色附加终态工具 `submit_<output_contract_id>`。该工具的 `parameters` 直接来自 `output_type.model_json_schema()`，因此 `Literal`、长度和嵌套字段约束会作为 JSON Schema（包括 `enum`）进入模型可见工具定义。终态工具必须单独调用；与其他工具同批调用会被拒绝。
9. 终态参数先经输出 Pydantic 协议校验，再经角色资源后处理校验；失败时把错误作为 tool result 返回，让同一角色继续修正。
10. 达到 `max_turns` 仍未提交合法结构化输出时，角色运行失败。

`intervention_worker` 不使用上述终态提交循环；它由专用 persistent branch runtime 执行，输出由程序从实际分支事件计算。

---

## 1. Failure Analyst（`failure_analyst`）

### 1.1 关系图位置

#### 路由至当前角色

- `[确定性 incumbent 评估]`：`EVALUATE_INCUMBENT` effect 成功完成时，无附加分支条件，Controller 固定创建 `ANALYZE_FAILURE`，进而调用该角色。

#### 从当前角色路由出去

- `[Hypothesis Researcher]`：该角色 effect 成功返回任意合法 `FailureDirection` 时，Controller 无条件创建 `RESEARCH_HYPOTHESIS`。
- `[Controller 重试/暂停]`：角色 effect 抛出异常时，若 `item.attempt <= config.max_work_retries` 则创建同种 work 的 retry；否则按 Controller 失败预算暂停。这不是模型输出分支。

### 1.2 输入协议

```python
class FailureAnalystInput(TeacherPayload):
    analysis_focus: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
    )
    # 可选分析焦点；为 None 时由角色自行选择证据最强的有界行为模式。
```

Controller 当前构造值：

```python
{
    "analysis_focus": work.payload.get("analysis_focus"),
}
```

### 1.3 输出协议

```python
class FailureDirection(TeacherPayload):
    pattern: str = Field(min_length=1, max_length=400)
    # 可直接观察到的单一 Actor 失败行为序列。

    applicability: str = Field(min_length=1, max_length=300)
    # 该失败模式成立的任务或证据状态边界。

    caveats: list[str] = Field(min_length=1, max_length=3)
    # 一至三个尚未排除的混杂因素或诊断限制。

    evidence_refs: list[str] = Field(min_length=2, max_length=4)
    # 两至四个直接检查过的 `example_id/replicate_id` 轨迹引用。
```

允许取值与约束：

- 所有字符串均自动 strip，协议拒绝未知字段。
- `evidence_refs` 长度为 2–4，必须唯一。
- 每项必须恰好为两个非空片段组成的 `example_id/replicate_id`。
- `caveats` 只有列表长度约束，没有元素级 `min_length`；因此只含空白的元素经全局 strip 后仍可能变成空字符串并通过该字段声明。相比之下，`pattern`、`applicability` 有字符串 `min_length`，`evidence_refs` 还有专门 validator 拒绝空片段。

后处理：

1. `resources.evaluation.validate_evidence_refs()` 要求每个输出引用确实通过 `get_actor_trajectory` 成功读取过。
2. effect 再次执行 `FailureDirection.model_validate()`。
3. 完整角色 artifact 写为 `failure_artifact`。
4. 输出内容本身不控制路由；合法输出一律进入 Hypothesis Researcher。

### 1.4 翻译后的提示词与组装

#### 系统提示词

~~~markdown

你是离线 Harness 演化系统中的 Failure Analyst。

**目标**

基于直接评估证据，识别且只识别一个有界、可观察的 Actor 行为失败。你的输出是诊断性交接，不是因果解释或干预设计。

**证据流程**

1. 只把紧凑资源摘要用于总体定位。
2. 列出稳定失败和不稳定案例。
3. 选择一个候选 Actor 行为序列，而不只是一个错误答案。
4. 在条件允许时检查至少两个相关逻辑案例。
5. 检查 2–6 条具体轨迹，优先跨不同逻辑案例。6 次轨迹读取是硬证据预算，不是目标；并行调用共享预算。默认 `behavior` 视图保留原生 reasoning、带内模型输出、动作、观察和结果。只有需要重复模型输入、provider 字段或内部运行时事件时才请求 `full`。
6. 只有当诊断依赖某能力是否已注册时才读取 Harness manifest。
7. 一旦两个独立案例支持同一模式，立即提交。

初始摘要有意不包含 token 成本。只有请求的分析焦点或已观察行为使效率成为合理失败维度时，才调用 `get_cost_summary` 和 `list_evaluation_cases_by_cost`。成本证据应使用 replicate 分布，而非整个报告的 token 总数。

**证据标准**

- 只能引用亲自检查的轨迹。
- 每个证据引用使用 `example_id/replicate_id`。
- retriever error 为零不能证明语料包含充分证据。
- 除非已检查案例的 evaluation 支持，否则不要声称 scorer 正确。
- 不得把观察范围外推到未检查的案例或轨迹。
- 区分 Actor 行为与 runner failure、tool failure、语料不支持、强制步数上限和评分歧义。

**输出协议**

- `pattern`：一个简洁、可观察的失败序列，只陈述 Actor 做了什么以及当时证据状态。
- `applicability`：模式适用的任务或证据状态；不得包含案例名称或无支持的总体性主张。
- `caveats`：1–3 个未解决的混杂因素或诊断限制；保留不确定性，不得把总体相关性改写成排除结论。
- `evidence_refs`：选择 2–4 条唯一、亲自检查且最清楚支持该模式的轨迹。

**禁止内容**

不得陈述理想行为，不得提出 Hook phase、提示词措辞、搜索查询策略、实体特定动作、答案、代码修改或实现细节。语义输出字段不得包含案例实体或答案。

提交前确认每个主张都有证据、每个引用均已打开，且结果仍是诊断而不是解决方案。

~~~

#### 用户提示词

~~~markdown

按规定证据流程分析评估。

角色输入：

```text
{{role_input}}
```

程序维护的紧凑资源摘要：

```text
{{resource_context}}
```

如果 `analysis_focus` 为 null，选择现有证据支持最强的有界行为模式。提交结构化结果前必须使用工具。

~~~

#### 本角色组装补充

- `resource_context` 只包含 `{"evaluation": failure_analyst_context}`。
- 绑定输入时设置唯一轨迹读取预算为 6。
- 输出终态工具名为 `submit_failure_direction`。

### 1.5 可调用工具

```python
def list_evaluation_cases(
    page: int = 1,
    page_size: int = 10,
    stability: Literal[
        "any", "stable_failure", "unstable", "stable_correct", "unresolved"
    ] = "any",
) -> ToolResult:
    """List logical evaluation cases without loading full trajectories."""

def list_evaluation_cases_by_cost(
    page: int = 1,
    page_size: int = 10,
    stability: Literal[
        "any", "stable_failure", "unstable", "stable_correct", "unresolved"
    ] = "any",
    token_metric: Literal[
        "input_tokens", "output_tokens", "total_tokens",
        "actor_total_tokens", "hook_total_tokens"
    ] = "total_tokens",
    order: Literal["descending", "ascending"] = "descending",
) -> ToolResult:
    """List logical cases ordered by mean replicate token usage."""

def get_cost_summary() -> ToolResult:
    """Read replicate-level token coverage and distribution statistics."""

def get_evaluation_case(example_id: str) -> ToolResult:
    """Read one logical example's evaluation and replicate directory."""

def get_actor_trajectory(
    example_id: str,
    replicate_id: str,
    view: Literal["behavior", "full"] = "behavior",
) -> ToolResult:
    """Read one Actor trajectory at behavior or full diagnostic detail."""

def get_harness_manifest() -> ToolResult:
    """Read the current Actor Harness manifest."""

def submit_failure_direction(
    pattern: str,
    applicability: str,
    caveats: list[str],
    evidence_refs: list[str],
) -> ToolResult:
    """提交并校验最终 failure_direction@1；由运行时自动注入。"""
```

两个分页工具的模型可见参数 schema 还要求 `page >= 1`、`1 <= page_size <= 20`；上述 `Literal` 已列出其余 choices。

### 1.6 代码上的额外机制

- 角色只能看到 Experience Set 的评估、rollout 和当前 accepted Harness。
- `get_actor_trajectory` 的 6 条唯一轨迹预算在资源层执行，并行工具调用也共享计数。
- Failure Analyst 输出中引用未读轨迹会使终态工具返回 validation error，而不是结束角色。
- 该角色没有“无方向”输出；协议强制至少提交一个 FailureDirection。因此新 Controller 不再具有旧 Runner 中“Critic 没有 problem direction”的正常分支。

---

## 2. Hypothesis Researcher（`hypothesis_researcher`）

### 2.1 关系图位置

#### 路由至当前角色

- `[Failure Analyst]`：Failure Analyst effect 成功完成时，无输出值分支，固定路由至该角色。
- `[Intervention Worker]`：`output["result_kind"] == "unsupported_hypothesis"` 时，`hypothesis_revision += 1`；若新值 `<= config.max_hypothesis_revisions`，以 `feedback_source="intervention_worker"` 续接原 Researcher 会话。
- `[Evidence Reviewer]`：`output["decision"] in {"revise", "reject"}` 时，`hypothesis_revision += 1`；若新值 `<= config.max_hypothesis_revisions`，以 `feedback_source="evidence_reviewer"` 续接原 Researcher 会话。

#### 从当前角色路由出去

- `[确定性 Trial Selector]`：任意合法 `InterventionHypothesis` 返回后，无输出值分支，固定路由至 `SELECT_TRIAL`。
- `[流程终止]`：上述 Worker/Reviewer 回路使 `hypothesis_revision > config.max_hypothesis_revisions` 时，不再调用该角色，流程以 revision budget exhausted 结束。
- `[Controller 重试/暂停]`：该角色 effect 抛出异常时，若 `item.attempt <= config.max_work_retries` 则创建同一 `RESEARCH_HYPOTHESIS` work 的 retry；否则按 Controller failure budget 暂停。

### 2.2 输入协议

```python
class HypothesisResearcherInput(TeacherPayload):
    problem_direction: FailureDirection
    # Failure Analyst 已冻结且带直接轨迹引用的问题方向。

class FailureDirection(TeacherPayload):
    pattern: str = Field(min_length=1, max_length=400)
    # 已观察失败序列。

    applicability: str = Field(min_length=1, max_length=300)
    # 失败模式适用边界。

    caveats: list[str] = Field(min_length=1, max_length=3)
    # 尚未排除的限制或混杂因素。

    evidence_refs: list[str] = Field(min_length=2, max_length=4)
    # Researcher 被允许读取的冻结轨迹集合。
```

初次调用时输入来自 `failure_artifact.output`；续接时保持原 `role_input` 不变，只向原 transcript 增加结构化 Worker 或 Reviewer feedback。

### 2.3 输出协议

```python
HookPhaseName = Literal[
    "post_prompt", "post_model", "post_parse",
    "pre_tool", "post_tool", "pre_final",
]

class HypothesisEvaluationSpec(TeacherPayload):
    primary_signal: str = Field(min_length=1, max_length=200)
    # 每条已激活 trial 要观察的主信号。

    success_condition: str = Field(min_length=1, max_length=250)
    # 主信号在单条 trial 上满足成功的条件。

    falsifier: str = Field(min_length=1, max_length=250)
    # 在单条已激活 trial 上反驳预测响应的观察。

    secondary_metrics: list[
        Annotated[str, Field(min_length=1, max_length=160)]
    ] = Field(default_factory=list, max_length=3)
    # 最多三个非因果效用或成本指标。

class InterventionPhaseDirective(TeacherPayload):
    phase: HookPhaseName
    # 本条干预发生的 Hook phase。

    activation_condition: str = Field(min_length=1, max_length=350)
    # 可从该 phase 可见状态判断的激活条件。

    instruction: str = Field(min_length=1, max_length=600)
    # 条件成立时 Worker 执行的有界临时指令。

    expected_effect: str = Field(min_length=1, max_length=300)
    # 该 phase 动作预期造成的即时 Actor 行为。

    max_activations: int = Field(default=1, ge=1, le=4)
    # 该 phase 在一条 Actor 分支中的最大激活次数。

class InterventionHypothesis(TeacherPayload):
    fork_phase: HookPhaseName
    # 重建 inclusive prefix 并开始试验的 phase。

    phase_plan: list[InterventionPhaseDirective] = Field(
        min_length=1,
        max_length=4,
    )
    # 按因果顺序排列的一至四条、phase 唯一的干预计划。

    evaluation: HypothesisEvaluationSpec
    # trial 执行前冻结的单条试验观察协议。

    applicability: str = Field(min_length=1, max_length=300)
    # 假设适用的任务与运行时状态。
```

允许取值与约束：

- `fork_phase` 和每个 `phase_plan[].phase` 仅允许上述 6 个可恢复 phase。
- `phase_plan` 长度为 1–4，phase 不得重复。
- `phase_plan[0].phase` 必须等于 `fork_phase`。
- `max_activations` 为 1–4。
- `secondary_metrics` 最多 3 项且必须唯一；每项字符串长度为 1–160。
- before-validator 允许把旧版单 phase 字段 `trigger/trigger_phase/intervention/predicted_actor_response` 归一成新版 `phase_plan`。

后处理：

1. 输入绑定把 Researcher 的轨迹读取 allowlist 冻结为 `problem_direction.evidence_refs`。
2. 提交前必须读取 allowlist 中全部轨迹。
3. 提交前必须调用 `get_intervention_capabilities`。
4. effect 再次校验协议，写入新的 `hypothesis_artifact`；续接会话时该引用替换旧版本。
5. Controller 重置 `trial_count=0`、`assignment_count=0`、`used_assignments=[]` 和 `prior_obligation=None` 后进入 Trial Selector。

### 2.4 翻译后的提示词与组装

#### 系统提示词

~~~markdown

你是离线 Harness 演化系统中的 Hypothesis Researcher。

**目标**

把冻结的 Failure Analyst 方向转化为且只转化为一个具体、可证伪的 Teacher 软干预假设。当单 phase 无法表达所提机制时，一个假设可以包含一条短的多 phase 因果链：

```text
可恢复 fork → phase 局部干预 → 可观察 Actor 响应
```

不要判断该假设是否已经获得支持。

**规定流程**

1. 保留问题方向的 applicability 和 caveats；不得扩大普遍性或静默消除不确定性。
2. 使用默认 `behavior` 视图各检查一次每条被引用轨迹。
3. 选择 trigger 或 action 前必须调用 `get_intervention_capabilities`。
4. 选择一个可恢复 `fork_phase`，第一项干预可应用于 inclusive reconstructed prefix。
5. 按因果顺序指定 1–4 个唯一 phase directive；每项包含可观察条件、有界干预指令、即时预期效果和 phase 局部激活预算。
6. 只有前一观察或修改必须影响后续 Actor 决策时才使用多 phase；不得捆绑无关实验。
7. 为完整计划预注册一个主观察、单 trial 成功条件和单 trial falsifier。次要指标可衡量效用或成本，但不能成为额外因果主张。
8. 假设完整后立即提交。

修订 continuation 期间可能附加已审阅 Intervention trials。只有权威 Worker/Reviewer feedback 无法在不看精确 source/branch event 的情况下解决时才使用 `get_trial_evidence`。该工具返回完整轨迹，只移除非判断性运行时元数据。不得重新裁决 Reviewer 已经解决的证据来取代 Reviewer。

**输出协议**

- `fork_phase`：必须且只能是能力目录中的 `post_prompt`、`post_model`、`post_parse`、`pre_tool`、`post_tool` 或 `pre_final`，且等于 `phase_plan[0].phase`。
- `phase_plan[].phase`：由同一持久 Worker transcript 处理的唯一 Hook phase。
- `phase_plan[].activation_condition`：可由该 phase 目录化状态观察的条件。
- `phase_plan[].instruction`：临时上下文或控制意图，不含插件实现细节。
- `phase_plan[].expected_effect`：该 phase 动作立即导致的可观察 Actor 行为，而非总体 accuracy。
- `phase_plan[].max_activations`：小的正数界限；除非重复激活对因果主张不可缺少，否则使用 1。
- `evaluation.primary_signal`：每条已激活 trial 中测量的 trace event 或派生观察。
- `evaluation.success_condition`：预期单 trial 值。
- `evaluation.falsifier`：一个与预测响应矛盾的已激活 trial 观察。
- `evaluation.secondary_metrics`：最多三个非因果效用或成本指标，例如 answer score、tool calls 或 total tokens。
- `applicability`：假设适用的任务和运行时状态。

跨 trial 的总体阈值由 Evidence Reviewer 决定；Candidate Reviewer 后续判断任务收益与回归。

**禁止内容**

不得包含案例答案、具名案例实体、案例特定查询、实体路径、隐藏 gold evidence、预期 accuracy、插件文件、Python 代码或未支持的运行时能力。除非能力目录明确说明，否则 native reasoning 对 Hook 不可见。

Teacher Worker 可以对 phase 可见快照做语义判断以决定条件是否成立。这验证软干预，不表示该判断可以转移为确定性规则或有界 Actor Hook model。不得在此角色中声明实现选择；Mechanism Distiller 将根据 trial 证据审计。

提交前确认每条 phase directive 可执行、后续 directive 确实依赖同一分支、主信号衡量完整因果计划、falsifier 只检验当前假设。

~~~

#### 用户提示词

~~~markdown

开发一个有界、可证伪的软干预假设。

角色输入：

```text
{{role_input}}
```

程序维护的紧凑证据与 Actor 摘要：

```text
{{resource_context}}
```

提交前检查全部引用证据和干预能力目录。

~~~

#### 本角色组装补充

- 初次 `resource_context` 只含 Researcher 专用 evaluation 摘要。
- continuation 保持同一 `session_id`、system prompt 和冻结输入，把结构化反馈追加为新的 user message；它不是只在程序状态中传递的摘要。
- 输出终态工具名为 `submit_intervention_hypothesis`。

#### `feedback_source="intervention_worker"` 时实际追加的 continuation user 提示词

~~~markdown

作为现有会话中的同一个 Teacher 角色继续。
被分配的干预无法执行冻结假设，因为存在假设层面的能力不匹配。修订假设，使其只使用受支持的可观察状态和动作。

权威结构化反馈：
```json
{{feedback_event 的 ensure_ascii=False、indent=2 JSON}}
```

~~~

#### `feedback_source="evidence_reviewer"` 时实际追加的 continuation user 提示词

~~~markdown

作为现有会话中的同一个 Teacher 角色继续。
干预证据已经审阅。保留先前假设中有支持的部分，直接回应审阅决定和下一项 obligation，并提交一个完整的修订假设。

权威结构化反馈：
```json
{{feedback_event 的 ensure_ascii=False、indent=2 JSON}}
```

~~~

### 2.5 可调用工具

```python
def get_actor_trajectory(
    example_id: str,
    replicate_id: str,
    view: Literal["behavior", "full"] = "behavior",
) -> ToolResult:
    """Read one Actor trajectory at behavior or full diagnostic detail."""

def get_intervention_capabilities() -> ToolResult:
    """Read source-derived trial phases, observations, actions and limits."""

def list_trial_evidence() -> ToolResult:
    """List explicitly attached Intervention trial references and facts."""

def get_trial_evidence(trial_ref: str) -> ToolResult:
    """Read full source and branch runs with non-judgment metadata removed."""

def submit_intervention_hypothesis(
    fork_phase: HookPhaseName,
    phase_plan: list[InterventionPhaseDirective],
    evaluation: HypothesisEvaluationSpec,
    applicability: str,
) -> ToolResult:
    """提交并校验最终 intervention_hypothesis@3；由运行时自动注入。"""
```

`get_intervention_capabilities()` 没有 phase 入参，因此函数签名本身不使用 `Literal`。调用后的模型可见 JSON 会在 `phases[]` 中逐项列出六个可恢复 phase，并为每项给出 phase-local `stage` key/type/stability/note 和 `native_reasoning_visible=False`；`actions[]` 还列出每个动作的 compatible phases、effect 和 persistence。该目录由 `recoverable_prefix_phases()`、`STAGE_KEYS_BY_PHASE` 和 `InterventionActionName` 动态构建，不是提示词私有常量。

该工具返回的完整字段形状如下（为便于审核，英文 `note`/`effect` 字符串值在下方译成中文，并非声称原始返回字节是中文）；`ALL_PHASES` 在实际 JSON 中展开为六项字符串数组，`actor` 则由工具在基础 catalog 上动态追加：

```python
ALL_PHASES = [
    "post_prompt", "post_model", "post_parse",
    "pre_tool", "post_tool", "pre_final",
]

{
    "schema_version": 2,
    "source_contracts": [
        "core.hooks.HookPhase",
        "core.hooks.STAGE_KEYS_BY_PHASE",
        "adapter.intervention.prefix.recoverable_prefix_phases",
        "teacher.contracts.InterventionActionName",
        "teacher.hook_api.query_hook_api",
    ],
    "execution": {
        "one_action_per_activation": True,
        "multiple_phases_per_trial": True,
        "same_worker_transcript_across_activations": True,
        "maximum_phase_directives": 4,
        "unique_phase_directives": True,
        "action_application": "current_hook_activation",
        "actor_continues_from_selected_prefix": True,
        "teacher_loop_inside_actor": False,
    },
    "observability": {
        "selected_prefix": [
            "selector.step", "selector.phase", "question",
            "model_input.messages", "active_stage",
        ],
        "active_stage": "phase-specific values listed under each phase.stage",
        "native_reasoning": "trace_only_not_hook_visible",
        "inband_thinking": (
            "available through raw model text at post_model and "
            "ParsedOutput at post_parse"
        ),
    },
    "phases": [
        {
            "phase": "post_prompt",
            "stage": [{
                "key": "stage.model_input", "type": "ModelInput",
                "stability": "stable",
                "note": "即将进行的模型生成实际使用的值。",
            }],
            "native_reasoning_visible": False,
        },
        {
            "phase": "post_model",
            "stage": [{
                "key": "stage.raw_model_output", "type": "str",
                "stability": "stable", "note": "解析前的原始模型文本。",
            }],
            "native_reasoning_visible": False,
        },
        {
            "phase": "post_parse",
            "stage": [
                {
                    "key": "stage.parsed_output", "type": "ParsedOutput",
                    "stability": "stable",
                    "note": "POST_PARSE 后由 loop 消费的已解析分支值。",
                },
                {
                    "key": "stage.parser_input", "type": "str",
                    "stability": "stable",
                    "note": "parser 已消费的文本；替换它不会重新运行解析。",
                },
            ],
            "native_reasoning_visible": False,
        },
        {
            "phase": "pre_tool",
            "stage": [{
                "key": "stage.tool_call", "type": "ToolCall",
                "stability": "stable",
                "note": "PRE_TOOL 时控制执行；POST_TOOL 时该调用已经运行。",
            }],
            "native_reasoning_visible": False,
        },
        {
            "phase": "post_tool",
            "stage": [
                {
                    "key": "stage.tool_call", "type": "ToolCall",
                    "stability": "stable",
                    "note": "PRE_TOOL 时控制执行；POST_TOOL 时该调用已经运行。",
                },
                {
                    "key": "stage.tool_result", "type": "ToolResult",
                    "stability": "stable",
                    "note": "POST_TOOL 后记录到历史中的工具结果。",
                },
            ],
            "native_reasoning_visible": False,
        },
        {
            "phase": "pre_final",
            "stage": [{
                "key": "stage.final_decision", "type": "FinalDecision",
                "stability": "stable",
                "note": "在 PRE_FINAL 接受或推迟已解析的最终答案。",
            }],
            "native_reasoning_visible": False,
        },
    ],
    "actions": [
        {
            "name": "append_system_message",
            "effect": "在分支继续前追加一条 system-role 指令。",
            "compatible_phases": ALL_PHASES,
            "persistence": "branch_prefix",
        },
        {
            "name": "append_user_message",
            "effect": "在分支继续前追加一条 user-role 指令。",
            "compatible_phases": ALL_PHASES,
            "persistence": "branch_prefix",
        },
        {
            "name": "defer_final_answer",
            "effect": "拒绝当前 final candidate 一次、追加反馈并请求下一次生成。",
            "compatible_phases": ["pre_final"],
            "persistence": "branch_prefix",
        },
        {
            "name": "no_op",
            "effect": "不改变 Actor context，继续该分支。",
            "compatible_phases": ALL_PHASES,
            "persistence": "none",
        },
        {
            "name": "replace_system_instruction",
            "effect": "保留非 system messages 和工具证据，替换 system instruction。",
            "compatible_phases": ALL_PHASES,
            "persistence": "branch",
        },
    ],
    "actor": {
        "harness_id": "当前 manifest.harness_id 或 null",
        "tools": ["当前 manifest.tools[].instance_id", "..."],
    },
}
```

终态 `submit_intervention_hypothesis` 的 JSON Schema 又会把 `fork_phase` 与每个 `phase_plan[].phase` 暴露为相同六值 `enum`。因此模型在系统提示词、必调工具结果和终态工具 schema 三处都能看到范围。

### 2.6 代码上的额外机制

- 初次运行只能读取 Analyst 引用的轨迹，且 gold answer 会从允许视图中移除。
- 核心 `HookPhase` 还定义了 `pre_prompt` 与 `on_error`，但它们不属于可重建 Actor-visible prefix 的 `HookPhaseName`；Researcher 协议只允许上述六项。
- Worker/Reviewer 修订不是新会话：原 transcript、输出历史、反馈历史和资源读取状态均被恢复。
- Controller 对修订后的假设重新清零 trial 与 assignment 计数，旧 trial artifact 仍可附加给 continuation 供精确查证。
- `Evidence Reviewer decision == "reject"` 不会直接终止，而是与 `"revise"` 一样路由回 Researcher；真正是否停止由 hypothesis revision budget 决定。

---

## 3. Intervention Worker（`intervention_worker`）

### 3.1 关系图位置

#### 路由至当前角色

- `[确定性 Trial Selector]`：`SELECT_TRIAL` effect 返回 `outcome["status"] == "selected"` 时，Controller 把 `outcome["assignment"]` 写入 payload，并创建 `EXECUTE_TRIAL` 调用该角色。

#### 从当前角色路由出去

- `[确定性 Trial Selector]`：`output["result_kind"] == "unsuitable_assignment"` 且 `payload["assignment_count"] < config.max_trial_assignments` 时，重新选择 prefix。
- `[流程终止]`：`output["result_kind"] == "unsuitable_assignment"` 且 `payload["assignment_count"] >= config.max_trial_assignments` 时，以 assignment budget exhausted 结束。
- `[Hypothesis Researcher]`：`output["result_kind"] == "unsupported_hypothesis"` 且增加后的 `hypothesis_revision <= config.max_hypothesis_revisions` 时，续接 Researcher。
- `[Trial Reviewer / Evidence Reviewer]`：`output["result_kind"] == "executed"` 时，`trial_count += 1`，保存 `worker_artifact` 为 `trial_NNN`，创建 `REVIEW_EVIDENCE`；该 effect 先调用 Trial Reviewer，再调用 Evidence Reviewer。
- `[Controller 重试/暂停]`：`EXECUTE_TRIAL` effect 抛出异常时，若 `item.attempt <= config.max_work_retries` 则重试同一 work；否则按 failure budget 暂停。

### 3.2 输入协议

```python
class InterventionWorkerInput(TeacherPayload):
    hypothesis: InterventionHypothesis
    # 已冻结、不得由 Worker 修改的完整干预假设。

    trial_objective: str = Field(min_length=1)
    # 当前 trial 要解决的目标；可包含上一轮 Reviewer/Distiller obligation。

    example_id: str = Field(min_length=1)
    # 被分叉 Actor 轨迹的逻辑样本 ID。

    replicate_id: str = Field(min_length=1)
    # 被分叉 Actor 轨迹的 replicate ID。

    prefix_id: int = Field(ge=1)
    # 该轨迹中 inclusive reconstructed prefix 的正整数 ID。

    prohibited_content: list[str] = Field(default_factory=list)
    # 本次 Worker 动作额外禁止包含的内容。
```

其中 `hypothesis` 的字段结构见 2.3；Controller assignment 当前始终把 `prohibited_content` 设为空列表。

### 3.3 输出协议

```python
InterventionResultKind = Literal[
    "executed",
    "unsuitable_assignment",
    "unsupported_hypothesis",
]

class InterventionWorkerResult(TeacherPayload):
    result_kind: InterventionResultKind
    # 程序对本次分支是否执行干预及失败类型的分类。

    activated_phases: list[HookPhaseName] = Field(default_factory=list)
    # 计划中实际至少激活一次的 phase，按计划顺序排列。

    modified_phases: list[HookPhaseName] = Field(default_factory=list)
    # 实际执行了非 no-op 动作的 phase。

    unmet_phases: list[HookPhaseName] = Field(default_factory=list)
    # 计划中从未激活的 phase。
```

允许取值与约束：

- `result_kind` 协议允许上述三个值。
- 三个 phase 列表各自不得重复。
- `activated_phases` 与 `unmet_phases` 必须不相交。
- `modified_phases` 必须是 `activated_phases` 的子集。
- `executed` 必须至少有一个 `modified_phases`。
- 非 `executed` 不得包含 `modified_phases`。

当前正式运行时的实际生成规则：

```python
result_kind = "executed" if modified_phases else "unsuitable_assignment"
```

其中 `modified_phases` 来自 `intervention_changes` 中 action kind 不等于 `continue_without_change` 的 phase；`activated_phases` 来自 `activation_counts[phase] > 0`；`unmet_phases` 是计划 phase 与 activated phase 的差。

后处理：

1. 输出不是模型提交，而是 `_worker_result()` 从实际 artifact 生成。
2. 完整 trial artifact 保存 source、phase plan、activation budget/count、context changes、phase effects、branch run、comparison 和 Worker trace。
3. effect 再次校验 `InterventionWorkerResult`，写入 `worker_artifact`。

### 3.4 翻译后的提示词与组装

该角色 manifest 中虽然注册了普通 system/user 模板，但正式 `InterventionRoleRuntime` 根本不调用 `load_prompt_spec()` 或读取这两个模板；它只通过 manifest 核对角色和输出协议。实际模型 system prompt 直接读取 `activation_system.md`，初始化时先写入一条持久 user message，每次 Hook 激活再动态追加 activation user message。

#### Manifest system 提示词（专用 runtime 未加载）

~~~markdown

Intervention Worker 由专用持久分支运行时执行。一个 Teacher transcript 观察指定 inclusive prefix，以及同一 Student continuation 到达的每个已配置 Hook phase。

每次激活时，运行时提供当前 phase、phase 局部条件与指令、完整可见快照、先前 Worker 决策和一组有界终态动作。Worker 检查条件并只返回一个动作。无修改动作表示已观察 phase 但未改动 Actor。随后分支继续，直到 Actor 终止。

程序而不是模型最终断言负责分类 reached、modified 和 unmet phases，并产生 `intervention_worker_result@3`。另一个 Trial Reviewer 审阅完整轨迹。

绝不引入 golden answer、案例特定答案、现成搜索查询、隐藏证据路径或 Actor 可见上下文之外的事实。Worker 可以在激活内使用 Teacher 语义判断，但只能通过提供的有界动作工具修改 Actor，不得启动嵌套 AgentLoop。

~~~

#### Manifest user 提示词（专用 runtime 未加载）

~~~markdown

角色输入：

```text
{{role_input}}
```

程序提供的资源上下文：

```text
{{resource_context}}
```

专用 Intervention runtime 验证 assignment、重建 inclusive prefix，并执行完整多 phase 计划。

~~~

#### 实际首次 activation 前写入的持久 user message

~~~markdown

```text
Intervention intent:
{
  "trial_objective": {{task.trial_objective}},
  "applicability": {{task.hypothesis.applicability}},
  "evaluation": {{task.hypothesis.evaluation 的 JSON object}},
  "prohibited_content": {{task.prohibited_content}}
}

Configured Hook guidance:
{
  "{{phase}}": "Observable condition: {{activation_condition}}\nInstruction when satisfied: {{instruction}}\nExpected immediate effect: {{expected_effect}}"
}
```

其中两个 JSON 都使用 `ensure_ascii=False, indent=2`；guidance object 按冻结的 `phase_plan` 逐项构造。这条消息在构造 Worker 时写入 `_history`，先于任何 activation，并随同一 transcript 跨激活保留。

~~~

#### 实际 activation system 提示词

~~~markdown

你是监督一条 forked Actor 轨迹的 Intervention Worker。

干预计划已冻结。同一个 Worker transcript 会在每个配置的 Hook phase 恢复，使观察和决策可以跨 Actor generations 保留。每次激活会给出当前 phase、Actor step、phase 局部激活次数、可观察条件、指令和预期效果。

每次激活：

1. 需要时检查绑定的 Actor 上下文。
2. 判断 phase 局部可观察条件是否满足。
3. 满足时，执行实现给定指令的最小上下文或控制动作。
4. 不满足时调用 `continue_without_change`。
5. 只调用一个终态动作工具。该工具会立即把控制权交回 Actor，因此 tool call 后不得再写内容。

不得使用 golden answer、案例特定答案、现成搜索查询、隐藏证据路径或 Actor-visible snapshot 中不存在的信息。不得启动另一个 AgentLoop 或执行 Actor 工具。可以在 transcript 中保留先前激活的有用事实，但行动前必须重新检查当前 phase snapshot。

每个面向 Actor 的 action payload 必须可以原样复用于 applicability 边界内的另一案例。不得引用或点名从当前问题或 passages 复制的实体、数字、答案候选、标题或关系；不得提出查询文本、片段、搜索词或示例。动作可以用通用措辞重述冻结的 phase instruction，但不能更案例化。内部可以推理具体缺失证据，但动作必须把识别和检索都委托回 Actor。使用“剩余证据缺口”，不能使用当前实体或建议查询。若不加入案例特定内容就无法执行指令，调用 `continue_without_change`；不安全动作会使 trial 无效。调用终态动作前，检查 payload 原样复制到另一个适用案例时是否仍有意义。

运行时在 `{{tools}}` 处插入：“运行时会在当前 activation message 中列出本次 Hook 激活可用的精确工具，只能使用当前列表。”

先写简洁分析或意图，再写且只写一个完整 `<tool_call>` block。

~~~

#### 动态 activation user message

~~~markdown

每次激活追加：

```text
Hook activation {全局激活序号}: phase={phase},
actor_step={step}, phase_activation={当前phase次数}/{最大次数}.
Phase guidance:
Observable condition: {activation_condition}
Instruction when satisfied: {instruction}
Expected immediate effect: {expected_effect}
Available tools for this activation:
{本次工具的完整 tagged schema 定义}
检查所需上下文，然后只调用一个终态动作工具。
```

同一 `_history` 会跨 phase 和 Actor generation 保留。这里插入的不是工具名摘要，而是每个动态工具的模型可见 schema；因此 `role`、`persistence` 等 choices 和字段说明也随每次 activation 消息呈现。

~~~

### 3.5 可调用工具

这些工具不是 manifest 工具，而是每次激活动态创建。除 `inspect_actor_context` 外均为终态动作。

```python
def inspect_actor_context() -> ToolResult:
    """Read the complete source prefix, current Actor state, trace and stage values."""

def append_context_message(
    role: Literal["system", "user", "assistant", "tool"],
    content: str,
    persistence: Literal["next_generation", "branch"] = "next_generation",
) -> ToolResult:
    """Add a message to Actor context and end the current Hook activation."""

def replace_model_input(
    system_instruction: str,
    user_instruction: str = "",
) -> ToolResult:
    """Rewrite Actor instructions without serializing its complete message list."""

def defer_final_answer(
    feedback: str,
    reason: str = "",
) -> ToolResult:
    """Reject the current final candidate and request another Actor generation."""

def accept_final_answer(
    answer: str,
    reason: str = "",
) -> ToolResult:
    """Accept an explicit final answer at an active pre-final Hook."""

def continue_without_change(reason: str) -> ToolResult:
    """Leave Actor context unchanged and end the current Hook activation."""
```

工具可用性：

- `defer_final_answer` 与 `accept_final_answer` 只在 snapshot 的 active stage 含 `final_decision` 时注册。
- 其余工具在每次 activation 均注册。
- 该角色没有 `submit_intervention_worker_result`；结果由程序生成。

Researcher 读取的 capability catalog 与 Worker 的实际动态工具不是同一命名层：catalog 的 `append_user_message`/`append_system_message` 对应 `append_context_message(role=...)`，`replace_system_instruction` 对应 `replace_model_input`，`no_op` 对应 `continue_without_change`。实际 Worker 还额外提供 `accept_final_answer`，且 `append_context_message.role` 也允许 `assistant`/`tool`，所以执行工具面比 catalog 的研究协议更宽；这是当前代码实现中的显式差异。

### 3.6 代码上的额外机制

- 运行前根据 `example_id/replicate_id/prefix_id` 重建 prefix，并强制 `boundary["phase"] == hypothesis.fork_phase`。
- Student 分支使用 `STUDENT_*` 模型；Worker 使用 `TEACHER_*` 模型。
- 每个 phase 的 guidance 与 activation budget 由冻结假设直接生成。
- 每次 activation 最多运行 `max_steps_per_activation` 个 Teacher step，必须以一个终态动作结束。
- Worker 不能直接运行 Actor tool；终态动作返回后才由 Actor loop 继续。
- `defer_final_answer`/`accept_final_answer` 会先验证当前 active stage 及 replacement shape。
- 程序可选使用 TeacherBinaryJudge 比较分支答案，但 Worker 不据此自报结果。
- `InterventionWorkerResult` 的输出 JSON Schema 只用于 artifact 的 `schema_digest` 和程序侧输出校验，不会作为终态工具 schema 展示给 Worker 模型；Worker 模型只看到 activation system/user 消息和当次动态工具 schema。
- **协议—实现差异**：协议和 Controller 都处理 `unsupported_hypothesis`，但当前 `_worker_result()` 没有生成该值的分支。因此正式生产路径中 Worker → Researcher 的 `unsupported_hypothesis` 回路目前不可达。

---

## 4. Trial Reviewer（`trial_reviewer`）

### 4.1 关系图位置

#### 路由至当前角色

- `[Intervention Worker]`：`InterventionWorkerResult.result_kind == "executed"` 时，Controller 创建 `REVIEW_EVIDENCE`。该 effect 对 `_trial_paths(work)` 中每个 trial 逐一处理；若对应 `trial_review_{index:03d}_artifact` 不在 `work.input_refs` 中，则调用该角色。
- `[已持久化 Trial Reviewer artifact]`：若上述 key 已存在，则不调用模型，而是校验 artifact 的冻结 hypothesis 和 `trial_ref` 后直接复用。

#### 从当前角色路由出去

- `[Trial Reviewer]`：当前 trial 完成且仍有下一条 trial 时，effect 在循环中调用下一实例；各实例相互独立。
- `[Evidence Reviewer]`：全部 trial 都已有合法 `TrialReview` 后，无输出值分支，effect 固定调用 Evidence Reviewer。

Trial Reviewer 自身没有 Controller `WorkKind`，它是 `REVIEW_EVIDENCE` effect 内部的逐 trial 子角色，因此没有“单个 Trial Reviewer”级别的 retry work 或独立状态转移。若其调用导致整个 effect 抛异常，则 `[Controller 重试/暂停]`：`item.attempt <= config.max_work_retries` 时重试整个 `REVIEW_EVIDENCE` work（包括该 effect 的逐 trial 审阅流程），否则按 failure budget 暂停。

### 4.2 输入协议

```python
class TrialReviewerInput(TeacherPayload):
    hypothesis: InterventionHypothesis
    # 本批 evidence cycle 中冻结的完整干预假设。

    trial_ref: str = Field(min_length=1)
    # 当前唯一被审阅 trial 的稳定引用。
```

资源配置只加载与 `trial_ref` 对应的一个 `trial_file`。

### 4.3 输出协议

```python
class TrialReview(TeacherPayload):
    trial_ref: str = Field(min_length=1)
    # 必须原样指向当前被分配 trial 的稳定引用。

    assessment: str = Field(min_length=1, max_length=4000)
    # 对该单条完整 Worker 轨迹的自包含事实分析。
```

允许取值与约束：

- 两个字段均为非空字符串，`assessment` 最长 4000 字符。
- 不存在 verdict 字段；该角色只产生单 trial 事实分析，不决定 hypothesis。

后处理：

1. 输入绑定把 TrialEvidenceStore 限定为输入 `trial_ref`。
2. 提交前 `validate_all_inspected()` 强制该 trial 已通过 `get_trial_evidence` 完整读取。
3. `review.trial_ref` 必须与唯一加载的 trial ref 完全相等。
4. `REVIEW_EVIDENCE` effect 再次检查输出 ref 与路径推导 ref 相等。
5. 所有 `TrialReview` 被序列化进 Evidence Reviewer 的 user-role `role_input`。

### 4.4 翻译后的提示词与组装

#### 系统提示词

~~~markdown

你是离线 Harness 演化系统中的 Trial Reviewer。

根据冻结假设，只审阅一条 Intervention Worker 轨迹。提交前必须为指定 trial 调用 `get_trial_evidence`。工具返回完整 source/branch 轨迹和确定性运行时事实，并刻意省略 Worker 撰写的任何摘要。

在简洁 assessment 中，只覆盖该轨迹支持的主张：

- assignment 是否处于 hypothesis applicability 边界内；
- 每个计划 phase 是否到达、条件是否可观察、Worker 是否在正确时机执行请求的修改；
- 即时 Actor 行为是否符合各 expected effect；
- 动作是否泄漏案例特定实体、查询文本、答案或 Actor 不可用证据；
- 显式 evaluation 与 cost 字段是否显示 outcome change；
- 限制 trial 的运行失败或缺失证据。

使用 `phase_effects` 判断事件顺序，使用完整 source/branch 轨迹做语义判断。确定性字段是权威信息。没有显式 score 时，不得由答案变化推断正确性。不得提出新干预，不得跨其他 trials 判断整个 hypothesis。

提交一个 `trial_review@1`，包含精确 assigned `trial_ref` 和一段自包含事实 assessment。

~~~

#### 用户提示词

~~~markdown

审阅唯一指定的 Intervention trial。

角色输入：

```text
{{role_input}}
```

程序维护的资源摘要：

```text
{{resource_context}}
```

读取指定完整轨迹，然后提交结构化 trial review。

~~~

#### 本角色组装补充

- `resource_context["trials"]` 只给出唯一 trial 的 `trial_count` 和 `trial_refs` 引用目录，不含 intent、phase plan、comparison 等 trial 事实。
- 完整 trial 只通过工具按需进入上下文。
- 每条 trial 使用全新的 Teacher 会话，不共享其他 Trial Reviewer 的 transcript。
- 输出终态工具名为 `submit_trial_review`。

### 4.5 可调用工具

```python
def get_trial_evidence(trial_ref: str) -> ToolResult:
    """Read full source and branch runs with non-judgment metadata removed."""

def submit_trial_review(
    trial_ref: str,
    assessment: str,
) -> ToolResult:
    """提交并校验最终 trial_review@1；由运行时自动注入。"""
```

源码中 `get_trial_evidence.trial_ref` 的 ToolArg 文案是“Trial reference returned by list_trial_evidence.”，但 Trial Reviewer manifest 没有注册 `list_trial_evidence`；本角色实际从 `role_input.trial_ref` 和 `resource_context` 获得该值。这是工具 schema 文案与本角色工具集合之间的不一致。

### 4.6 代码上的额外机制

- 每个 Trial Reviewer 只绑定一个 trial，无法通过该工具读取其他 trial。
- review artifact 可在恢复流程中复用，但复用前会核对 hypothesis JSON 和 trial ref，防止把旧 review 接到新假设。
- Trial Reviewer 没有结构化 phase finding；phase 局部标签由后续 Evidence Reviewer 输出。
- `assessment` 作为 role artifact 被嵌入下一角色的 user content，而不是 system content。

---

## 5. Evidence Reviewer（`evidence_reviewer`）

### 5.1 关系图位置

#### 路由至当前角色

- `[Trial Reviewer]`：`REVIEW_EVIDENCE` effect 已为 `_trial_paths(work)` 中全部 trial 获得合法 `TrialReview` 后，无其他分支条件，固定调用该角色。

#### 从当前角色路由出去

- `[确定性 Trial Selector]`：`output["decision"] == "continue"`，且 `trial_count < config.max_trials_per_hypothesis` 且 `assignment_count < config.max_trial_assignments` 时。
- `[Hypothesis Researcher]`：`output["decision"] in {"revise", "reject"}`，且增加后的 `hypothesis_revision <= config.max_hypothesis_revisions` 时。
- `[Mechanism Distiller]`：`output["decision"] == "ready_to_distill"` 时。
- `[流程终止]`：`decision == "continue"` 但 trial 或 assignment budget 已耗尽时。
- `[流程终止]`：`decision in {"revise", "reject"}` 但增加后的 `hypothesis_revision > config.max_hypothesis_revisions` 时。
- `[Controller 重试/暂停]`：Evidence Reviewer 位于 `REVIEW_EVIDENCE` effect 内；该 effect 抛异常且 `item.attempt <= config.max_work_retries` 时重试整个 work，否则按 failure budget 暂停。

### 5.2 输入协议

```python
class EvidenceReviewerInput(TeacherPayload):
    hypothesis: InterventionHypothesis
    # 当前 evidence cycle 中冻结的完整假设。

    aggregate_observations: dict[str, Any]
    # 程序从全部 trial artifacts 计算的确定性聚合观察。

    trial_reviews: list[TrialReview] = Field(min_length=1)
    # 各独立 Trial Reviewer 提交的至少一条事实审阅。

    prior_obligation: str | None = None
    # 上一轮 Evidence Reviewer、Mechanism Distiller 或 Candidate Reviewer 指定的最高价值待验证问题。
```

`aggregate_observations` 不是模型自由生成；由 `aggregate_trial_observations()` 从 trial artifact 计算。

### 5.3 输出协议

```python
EvidenceDecision = Literal[
    "continue", "revise", "reject", "ready_to_distill",
]

PhaseEvidenceStatus = Literal[
    "supported",
    "unsupported",
    "not_reached",
    "contaminated",
    "inconclusive",
]

class PhaseEvidenceFinding(TeacherPayload):
    phase: HookPhaseName
    # 被判断的冻结 phase。

    status: PhaseEvidenceStatus
    # 该 phase 的局部证据状态。

    assessment: str = Field(min_length=1, max_length=500)
    # 支持局部状态的简短事实判断。

class EvidenceReview(TeacherPayload):
    decision: EvidenceDecision
    # 对整个冻结假设的下一步决定。

    phase_findings: list[PhaseEvidenceFinding] = Field(
        default_factory=list,
        max_length=4,
    )
    # 按冻结 phase plan 顺序给出的逐 phase 判断。

    assessment: str = Field(min_length=1, max_length=1200)
    # 跨 trial 的总体证据判断。

    key_risk: str | None = Field(default=None, max_length=500)
    # 当前最关键风险；可为空。

    next_obligation: str | None = Field(default=None, max_length=400)
    # `continue` 时下一条必须验证的单一 obligation。
```

允许取值与约束：

- `decision` 只允许 `continue/revise/reject/ready_to_distill`。
- 每个 `status` 只允许上述五值。
- `phase_findings` 最多 4 项，phase 不得重复。
- 资源后处理进一步要求 `phase_findings.phase` 序列与冻结 `hypothesis.phase_plan` 完全一致；因此当前实际必须每个 phase 恰好一项且顺序相同。
- `decision == "continue"` 时 `next_obligation` 必填。
- `decision in {"reject", "ready_to_distill"}` 时 `next_obligation` 必须为空。
- `decision == "revise"` 对 `next_obligation` 没有协议级必填/禁止要求。
- `key_risk/next_obligation` 输入为 `None`、数值 `0` 或字符串 `""/"0"/"null"/"none"/"n/a"` 时会归一为 `None`。

后处理：

1. 严格检查逐 phase 覆盖和顺序。
2. effect 写入 `reviewer_artifact`，同时保留所有 `trial_review_*_artifact`。
3. Controller 把 `output.get("next_obligation")` 写回 `payload["prior_obligation"]`，再按 `decision` 路由。
4. `reject` 并非直接终态，而是触发 Researcher revision；这是 Controller 明确行为。

### 5.4 翻译后的提示词与组装

#### 系统提示词

~~~markdown

你是离线 Harness 演化系统中的 Evidence Reviewer。

根据 user message 中独立的 `trial_review@1` assessments 与程序维护的 aggregate observations，判断一个冻结假设。每个 Trial Reviewer 只检查了一条完整 Worker 轨迹。不得发明 assessment 中不存在的事件。当语义 assessment 与确定性 aggregate 字段冲突时，以确定性字段为准并注明冲突。

跨 trials 比较一致性、适用性、phase 局部因果效果、泄漏、运行失败、显式结果变化和成本。一个成功 phase 或一个成功案例不能自动支持整个计划。按计划顺序为每个冻结 phase 提交恰好一个 `phase_findings`：

- `supported`：可信 trial 证据支持条件、忠实修改和预期效果；
- `unsupported`：直接证据与预期效果矛盾；
- `not_reached`：未观察到相关条件；
- `contaminated`：干预发生泄漏或超出冻结指令；
- `inconclusive`：现有证据不能决定。

整个 hypothesis 的决定与局部标签分开。机制有可信有用证据，且没有重要未解决 obligation 阻碍 distillation 时使用 `ready_to_distill`；对同一假设还需要一次有区分度的测试时使用 `continue`；机制或 applicability 必须改变时使用 `revise`；因果主张被反驳或不可接受泄漏使其无效时使用 `reject`。进入 `ready_to_distill` 不要求每个 phase 或 trial 都 supported。

不得提出替代干预内容。`continue` 必须给出一个最高价值 `next_obligation`；`revise` 把所需修改写入 `assessment`。没有显式 score 时不得声称正确。提交现有 `evidence_review@2`。

~~~

#### 用户提示词

~~~markdown

依据独立逐 trial assessments 审阅冻结假设。

角色输入：

```text
{{role_input}}
```

程序维护的资源摘要：

```text
{{resource_context}}
```

Trial reviews 是角色 artifacts，因此在这里作为 user content。提交一个聚合结构化 review。

~~~

#### 本角色组装补充

- 当前 `REVIEW_EVIDENCE` effect 每次使用新的 `runtime.run()`，没有调用代码中已实现的 `continue_reviewer()`。
- `resource_config` 为空，Evidence Reviewer 没有原始 trial 读取工具；只能使用输入中的 TrialReview 和 aggregate observations。
- 输出终态工具名为 `submit_evidence_review`。

### 5.5 可调用工具

该角色 manifest 没有业务工具，只有运行时自动注入的终态工具：

```python
def submit_evidence_review(
    decision: EvidenceDecision,
    phase_findings: list[PhaseEvidenceFinding],
    assessment: str,
    key_risk: str | None = None,
    next_obligation: str | None = None,
) -> ToolResult:
    """提交并校验最终 evidence_review@2；由运行时自动注入。"""
```

### 5.6 代码上的额外机制

- 逐 trial 语义分析与跨 trial 聚合被强制拆成两个角色，Evidence Reviewer 无法直接读取完整轨迹。
- 冻结 phase 顺序由输入绑定写入资源状态，终态提交必须精确覆盖。
- 代码存在 `NativeChatTeacherRuntime.continue_reviewer()`，可把新 TrialReview 附加到同一 Reviewer transcript；但正式 Controller 当前没有使用它，而是每次重建新的 Evidence Reviewer 会话。
- `decision == "revise"` 的协议允许 `next_obligation` 有值或为空，但 Controller 路由 Researcher 时使用整个 output 作为 feedback，不依赖该字段。

---

## 6. Mechanism Distiller（`mechanism_distiller`）

### 6.1 关系图位置

#### 路由至当前角色

- `[Evidence Reviewer]`：`output["decision"] == "ready_to_distill"` 时。
- `[Compiler]`：`output["decision"] == "needs_revision"` 时，`mechanism_revision += 1`；若新值 `<= config.max_mechanism_revisions`，Controller 把 Compiler 的 `implementation_summary` 追加到 `capability_constraints` 后路由至该角色。
- `[Candidate Reviewer → Reject mechanism revision]`：Candidate Reviewer 的 `recommendation == "revise"`、promotion gate 未通过、`revision_target == "mechanism"`，且增加后的 `candidate_revision <= config.max_candidate_revisions` 时；`REJECT_CANDIDATE` effect 完成后把 `next_obligation` 追加到 `capability_constraints`，再路由至该角色。

#### 从当前角色路由出去

- `[确定性 Trial Selector]`：`output["decision"] == "needs_evidence"`，且 `trial_count < config.max_trials_per_hypothesis` 且 `assignment_count < config.max_trial_assignments` 时。
- `[Compiler]`：`output["decision"] == "distilled"` 时。
- `[流程终止]`：`output["decision"] == "not_distillable"` 时。
- `[流程终止]`：`decision == "needs_evidence"` 但 trial 或 assignment budget 已耗尽时。
- `[Controller 重试/暂停]`：`DISTILL_MECHANISM` effect 抛异常时，若 `item.attempt <= config.max_work_retries` 则重试同一 work；否则按 failure budget 暂停。

### 6.2 输入协议

```python
class MechanismDistillerInput(TeacherPayload):
    hypothesis: InterventionHypothesis
    # 经过 trial 验证的冻结干预假设。

    review: EvidenceReview
    # Evidence Reviewer 对假设和各 phase 的最终审阅。

    evidence_refs: list[str] = Field(min_length=1)
    # 支持本次提炼的 Intervention trial 引用。

    capability_constraints: list[str] = Field(default_factory=list)
    # Compiler 或 Candidate Reviewer 回传的无 Teacher 实现能力约束。
```

输入 validator 强制 `review.decision == "ready_to_distill"`；否则角色不能启动。

### 6.3 输出协议

```python
DistillationDecision = Literal[
    "distilled",
    "needs_evidence",
    "not_distillable",
]

class MechanismDistillation(TeacherPayload):
    decision: DistillationDecision
    # 提炼成功、仍需证据或根本不可提炼的终态选择。

    mechanism_ref: str | None = None
    # `distilled` 时指向本次运行中已验证 MechanismSpec 的稳定引用。

    rationale: str = Field(min_length=1)
    # 对当前提炼决定的非空理由。

    next_obligation: str | None = None
    # `needs_evidence` 时下一项具体、可测试的证据义务。
```

该角色通过工具另外构造以下被引用协议：

```python
DecisionEvaluator = Literal["deterministic", "hook_model"]

class MechanismPhaseRule(TeacherPayload):
    phase: HookPhaseName
    # 本条机制运行的 Actor Hook phase。

    trigger_condition: str = Field(min_length=1)
    # 只依赖本 phase 输入或声明状态的触发条件。

    decision_inputs: list[str] = Field(min_length=1)
    # 无 Teacher Harness 可读取的判定输入。

    decision_evaluator: DecisionEvaluator
    # 使用显式确定性规则或允许的 Hook model 做判断。

    action: str = Field(min_length=1)
    # 本 phase 要执行的一句局部动作。

    activation_budget: int = Field(default=1, ge=1)
    # 每条 Actor rollout 中该 rule 的最大激活次数。

class MechanismSpec(TeacherPayload):
    goal: str = Field(min_length=1)
    # 机制要产生的一般 Actor 行为目标。

    phase_rules: list[MechanismPhaseRule] = Field(min_length=1, max_length=4)
    # 一至四条 phase 唯一的机制规则；因果顺序由提示词要求，validator 不验证顺序。

    behavioral_pseudocode: str = Field(min_length=1, max_length=3000)
    # 权威的连续控制流、状态变化、委托工作和 fallback 描述。

    state_scope: str = Field(min_length=1)
    # 机制持久状态及其生命周期。

    fallback: str = Field(min_length=1)
    # 无法判定时的安全行为。

    expected_behavior: str = Field(min_length=1)
    # 激活后可观察的 Actor 过程效果。

    evidence_refs: list[str] = Field(min_length=1)
    # 支持该精确机制的 trial refs。

    required_capabilities: list[str] = Field(default_factory=list)
    # 编译和运行该机制所需能力。

    prohibited_behaviors: list[str] = Field(default_factory=list)
    # 编译后机制绝不能执行的行为。

    observability: list[str] = Field(default_factory=list)
    # 验证激活与效果所需的 trace 信号。

    known_limits: list[str] = Field(default_factory=list)
    # 证据已知但机制无法覆盖的边界。
```

允许取值与约束：

- `distilled`：`mechanism_ref` 必填，`next_obligation` 必须为空。
- `needs_evidence`：`next_obligation` 必填；协议不禁止 `mechanism_ref`。模型可以先验证 draft 获得真实 ref 再提交此 decision，但终态后处理不会 resolve/校验该 ref。
- `not_distillable`：协议没有额外字段互斥约束，也不会 resolve/校验随附的 `mechanism_ref`；因此它甚至可携带任意非空 ref，`next_obligation` 也不受互斥限制。
- `MechanismSpec.phase_rules` 长度为 1–4，phase 不得重复。
- 旧版单 phase MechanismSpec 可被 before-validator 归一到 `phase_rules`。

后处理：

1. `distilled` 时，终态校验要求 `mechanism_ref` 能在本次 `MechanismDraftStore` 中 resolve。
2. effect 从 artifact 的 `validated_mechanisms[mechanism_ref]` 再次校验 `MechanismSpec` 并独立写出 `mechanism_file`。
3. `needs_evidence` 时 Controller 把 `next_obligation` 写入 `prior_obligation`，进入新 trial。
4. `distilled` 时进入 Compiler；`not_distillable` 直接终止当前 run。

### 6.4 翻译后的提示词与组装

#### 系统提示词

~~~markdown

你是离线 Harness 演化系统中的 Mechanism Distiller。

判断已获支持的 Teacher 干预是否能由无 Teacher 访问的 Actor Harness 复现。检查支持 trials，审计 Teacher 使用的每个输入，移除案例特定措辞、答案、搜索查询、实体和证据路径。

**证据纪律**

- 区分 trial artifact 中直接存在的观察和你的推断；除非 artifact 明确测量，否则不得声称直接证据覆盖、正确性或安全弃答。
- 定量主张保留精确分子和分母。使用工具或遵循指令不是任务成功证据。
- 只提炼证据支持的最小行为；不得把未测试的语义层合并进已测试的静态层。

**可实现性纪律**

- 保留已支持干预必需的每个 phase link；不得把多 phase 因果链压成更强单 phase 动作，也不得增加未测试 phase。
- 每条 trigger 必须能由无 Teacher Harness 使用该 rule 的 `decision_inputs` 计算。“答案缺少直接支持”“桥接实体有歧义”“查询失败”等需要明确可用规则或模型能力。
- 只有所有 predicate 均有显式可复现定义时使用 `deterministic`；需要允许 Hook model 做有界语义分类时使用 `hook_model`。不同 phase 可以使用不同 evaluator。
- 不得把语义分类隐藏在关键词列表、正则表达式或未说明 helper predicate 中。
- 如果证据只支持 Teacher 判断，且未验证同一允许 Hook-model 判断，则返回 `needs_evidence` 或提炼更窄的无条件机制。
- 若一个具体有界 trial 可解决允许 Hook-model evaluator 的剩余不确定性，返回 `needs_evidence`；只有进一步证据也无法在现有 Harness 能力下实现时才用 `not_distillable`。
- 不得因为 Actor 收到反馈后能做某项工作，就把该语义工作分配给 deterministic Hook。
- phase trigger、action、状态交接、activation budget 和 fallback 必须描述一条连续控制路径。fallback 不得暗中撤销先前动作，也不得依赖该 phase 的 `decision_inputs` 和声明 persistent state 之外的信息。
- 若已测试干预依赖尚未被允许 Actor capability 复现的 Teacher judgment，返回 `needs_evidence` 或只提炼更窄的无条件机制。

每个可提炼机制必须产生一段实现无关 `behavioral_pseudocode`。自然语言字段描述 goal、evidence 和 constraints；伪代码是行为的权威连续描述。它不是形式语言，可以使用任何能消除以下歧义的简洁记法：

- 每条规则在哪个 Hook phase 运行；
- 条件读取哪些 phase 局部输入和持久状态；
- Hook 在每个重要分支按什么顺序修改什么；
- 哪些工作委托回 Actor；
- 重复激活、不确定性和 fallback 如何处理。

把它保持为最小效果规格：

- 描述已测试干预，而不是理想化的更强机制。
- 只写条件、有序效果、委托工作和终止行为；理由与解释写入自然语言字段，不作为伪代码注释。
- 倾向每个条件或效果一句直接陈述，不以多种形式重复同一 Actor feedback 或状态转移，也不以特定行数、关键词或固定 section 布局为目标。
- 每个必需 Hook effect 必须写成直接祈使动作；只出现在注释、标注、括号或解释中的效果不算控制流。
- 不使用注释标记或解释性注释；纯文本 bullet 可以使用，只要仍直接陈述条件和动作。
- 只描述 Hook 实际读取的值和实际改变的效果；保留当前 decision 是 no-op，不是重建 decision。
- 使用表达行为所需的最简单状态；one-shot 通常只需要 rollout-local boolean。
- 把 Hook phase 当作入口事件，不在伪代码内部重复把 phase 当运行时 predicate 检查。
- 只有控制流读取 phase input 时才提到它。
- Actor-facing feedback 只写一次，并明确它属于委托给 Actor 的工作。
- 不得发明试验中不存在的 corruption handling、unavailable-state handling 或 defensive branch；只在机制确有不确定性时使用声明的 fallback。
- one-shot mechanism 的 already-consumed no-op 通常就是 fallback；除非引用 trial 观察到，否则不增加 state corruption、API failure、context capacity、missing runtime 等基础设施 fallback。
- 抽象效果使用普通行为动词，不发明看似框架 API 的 code-like 或 snake_case operation。
- predicate 只能来自 `decision_inputs` 或声明状态；若必须使用 `is_supported(...)` 一类语义 predicate，要明确 evaluator 和可用 inputs。
- 不得包含 golden answer、案例实体、案例查询、source path、Python、框架类名、文件路径或实现提示。
- 保持简洁并不超过 3000 字符。

若机制可提炼：

1. 调用 `create_mechanism_draft`。
2. 按因果顺序为每个 supported phase 调用一次 `add_mechanism_phase`。
3. 调用 `complete_mechanism_draft` 填写跨 phase 伪代码、状态生命周期、安全 fallback 和预期过程行为。
4. 调用 `set_mechanism_constraints` 填写所需能力、禁止行为、trace 信号和已知限制。
5. 调用 `validate_mechanism_draft`，使用支持该精确机制的证据。
6. 返回 `distilled` 和已验证 `mechanism_ref`。

验证前审计：

- Hook 是否只用列出的输入就能判断 trigger；
- 每条 `decision_evaluator` 是否匹配实际 predicate，而不是实现捷径；
- 每条 deterministic rule 中看似语义的 predicate 是否都化为明确可复现规则；
- 每条 hook_model rule 是否由引用证据验证了相同判断任务，且 draft 中包含其 input、expected output 与 failure behavior；
- 每个条件是否只依赖该 rule 的 `decision_inputs` 或声明的 persistent state；
- 每个 state variable 是否被 `state_scope` 覆盖；
- `action` 是否为不含有序步骤列表的一句短句；
- one-shot 是否使用最简单的 consumed/not-consumed state；
- 每个 no-op path 是否保持当前 decision 不变；
- Actor feedback 是否只出现一次并明确为委托 Actor 的工作；
- action 与 fallback 是否都表示在控制流中；
- 每个 required state/context effect 是否是显式动作而非注释；
- 伪代码是否执行每条 phase rule 的 `activation_budget`；
- action 是否保持已测试措辞粒度且不插入 case fact；
- Hook action 与 Actor obligation 是否清楚分离；
- 伪代码是否避免 trial 未支持的行为；
- expected effect 是否只包含可观察过程行为和已测量 outcome；
- 未支持的语义能力是否被列为 known limit，而不是被假定可用。

一个具体测试可解决不确定性时返回 `needs_evidence`；成功行为根本依赖 Actor Harness 不可用的信息或判断时返回 `not_distillable`。

不得写 Python 或选择具体文件/类；MechanismSpec 只规定必须保留什么行为，Compiler 决定如何实现。

~~~

#### 用户提示词

~~~markdown

在证据允许时，把已支持干预提炼成无 Teacher 机制。

角色输入：

```text
{{role_input}}
```

程序维护的资源摘要：

```text
{{resource_context}}
```

返回 `distilled` 前，检查引用 trials 并使用 mechanism draft 工具。

~~~

#### 本角色组装补充

- `resource_context["trials"]` 只含 `trial_count/trial_refs`，不是 trial 事实摘要；`resource_context["mechanisms"]` 只含 `draft_count/validated_count` 两个计数，不包含进行中草稿正文。
- 输出终态工具名为 `submit_mechanism_distillation`。
- 终态只返回窄的 decision/ref；完整 MechanismSpec 存在 `validated_mechanisms` artifact 中。

### 6.5 可调用工具

```python
def list_trial_evidence() -> ToolResult:
    """List explicitly attached Intervention trial references and facts."""

def get_trial_evidence(trial_ref: str) -> ToolResult:
    """Read full source and branch runs with non-judgment metadata removed."""

def create_mechanism_draft(goal: str) -> ToolResult:
    """Create an empty no-Teacher mechanism draft."""

def add_mechanism_phase(
    draft_id: str,
    phase: str,
    trigger_condition: str,
    decision_inputs: list[str],
    decision_evaluator: Literal["deterministic", "hook_model"],
    action: str,
    activation_budget: int = 1,
) -> ToolResult:
    """Append one flat phase rule to a no-Teacher mechanism draft."""

def complete_mechanism_draft(
    draft_id: str,
    behavioral_pseudocode: str,
    state_scope: str,
    fallback: str,
    expected_behavior: str,
) -> ToolResult:
    """Complete one mechanism draft's shared state and control flow."""

def set_mechanism_constraints(
    draft_id: str,
    required_capabilities: list[str],
    prohibited_behaviors: list[str],
    observability: list[str],
    known_limits: list[str],
) -> ToolResult:
    """Attach bounded-execution and audit constraints to a mechanism draft."""

def validate_mechanism_draft(
    draft_id: str,
    evidence_refs: list[str],
) -> ToolResult:
    """Validate a complete mechanism draft and return its stable reference."""

def submit_mechanism_distillation(
    *,
    decision: DistillationDecision,
    mechanism_ref: str | None = None,
    rationale: str,
    next_obligation: str | None = None,
) -> ToolResult:
    """提交并校验最终 mechanism_distillation@1；由运行时自动注入。"""
```

工具层的 `add_mechanism_phase.phase` 源类型只是 `Annotated[str, ToolArg("Actor Hook phase where this rule observes state.")]`，没有 choices/enum。phase 合法值并非在该工具调用时校验，而是在 `validate_mechanism_draft()` 将完整 draft 解析为 `MechanismSpec` 时由 `HookPhaseName` 校验。`activation_budget` 的 ToolArg minimum 为 1；`behavioral_pseudocode` 的 ToolArg 说明最大 3000 字符，最终也由 MechanismSpec Field 强制。

### 6.6 代码上的额外机制

- MechanismSpec 不是直接由终态 tool 参数提交，而是通过状态化 draft 工具渐进构造并验证。
- `mechanism_ref` 是本次 run 局部引用；Controller 会将其解析成独立 JSON artifact，后续不依赖 Distiller 内存状态。
- 提示词要求检查 supporting trials，但程序没有 `validate_all_inspected()` gate；`validate_mechanism_draft(evidence_refs)` 也只要求非空字符串列表，不校验这些 ref 属于输入 `MechanismDistillerInput.evidence_refs`、实际存在或已被 `get_trial_evidence` 读取。
- draft validator 只检查 `phase_rules` 长度 1–4、phase 合法且唯一；不校验 phase 集合/顺序与 `hypothesis.phase_plan` 或 `review.phase_findings` 的 supported phases 对齐。因此“每个 supported phase、按因果顺序”均为提示词纪律，不是程序保证。
- `complete_mechanism_draft()` 每次都会把 `required_capabilities/prohibited_behaviors/observability/known_limits` 重置为空列表；若先 set constraints 后 complete，约束会被静默清空。提示词规定的“先 complete、后 set”可避免该副作用。
- Compiler 的 `needs_revision` 使用 `implementation_summary` 作为 capability constraint；协议没有单独的 revision-reason 字段。
- `not_distillable` 没有 revision 回路，直接结束整个 Controller run。

---

## 7. Compiler（`compiler`）

### 7.1 关系图位置

#### 路由至当前角色

- `[Mechanism Distiller]`：`output["decision"] == "distilled"` 时。
- `[确定性 Candidate Validation]`：`STAGE_CANDIDATE` 返回 `outcome["status"] == "validation_failed"`，`compiler_revision += 1`，且新值 `<= config.max_compiler_revisions` 时；Controller 把 `validation["errors"]` 写入 `validation_feedback` 后路由至该角色。
- `[Conformance Reviewer → Reject implementation revision]`：conformance aggregate `decision == "revise_implementation"`，增加后的 `candidate_revision <= config.max_candidate_revisions` 时；Reject effect 完成后将 compiler feedback 作为 `implementation_constraints` 路由至该角色。
- `[Candidate Reviewer → Reject implementation revision]`：Reviewer `recommendation == "revise"`、promotion gate 未通过、`revision_target == "implementation"`，且增加后的 `candidate_revision <= config.max_candidate_revisions` 时；Reject effect 完成后把 `next_obligation` 追加到 `implementation_constraints`。

#### 从当前角色路由出去

- `[Mechanism Distiller]`：`output["decision"] == "needs_revision"`，增加后的 `mechanism_revision <= config.max_mechanism_revisions` 时。
- `[确定性 Candidate Stage/Validation]`：`output["decision"] == "submitted"` 时。
- `[流程终止]`：`decision == "needs_revision"` 但增加后的 `mechanism_revision > config.max_mechanism_revisions` 时。
- `[Controller 重试/暂停]`：`COMPILE_CANDIDATE` effect 抛异常时，若 `item.attempt <= config.max_work_retries` 则重试同一 work；否则按 failure budget 暂停。

### 7.2 输入协议

```python
class CompilerInput(TeacherPayload):
    mechanism: MechanismSpec
    # 已验证、实现无关且无 Teacher 依赖的机制规格。

    implementation_constraints: list[str] = Field(default_factory=list)
    # Conformance/Candidate Reviewer 针对实现层回传的修复义务。

    validation_feedback: list[str] = Field(default_factory=list)
    # 上一次确定性 candidate validation 返回的错误。
```

`MechanismSpec` 与 `MechanismPhaseRule` 的完整字段见 6.3。

### 7.3 输出协议

```python
CompilerDecision = Literal["submitted", "needs_revision"]

class CompilerResult(TeacherPayload):
    decision: CompilerDecision
    # 已提交 candidate 或机制规格需要上游修订。

    candidate_ref: str | None = None
    # `submitted` 时指向本次 Compiler run 冻结候选的稳定引用。

    implementation_summary: str = Field(min_length=1)
    # 实现摘要；`needs_revision` 时也被 Controller 当作机制修订约束。

    unresolved_risk: str | None = None
    # 仍未消除、供后续 Candidate Reviewer 考虑的实现风险。
```

允许取值与约束：

- `decision` 只允许 `submitted/needs_revision`。
- `submitted` 时 `candidate_ref` 必填。
- `needs_revision` 时 `candidate_ref` 必须为空。
- 协议未要求 `submitted` 时 `unresolved_risk` 为空。

后处理：

1. 输入绑定根据 MechanismSpec 构造最小 `capability_packet`，并绑定到 Compiler workspace。
2. `submitted` 时终态校验要求 `candidate_ref` 能在本次 CompilerWorkspaceStore 中 resolve。
3. Compiler artifact 的 `resource_artifacts.compiler_candidate` 保存 workspace 中“最后一次”成功 finalize 的 candidate（exact changed files、parent/candidate digest、revision、validation 和 diff），不一定与输出所引用的 ref 相同；见 7.6 的对齐缺口。
4. `STAGE_CANDIDATE` 将 changed files 作为事务应用到 Version Store pending iteration，并核对 digest。
5. stage 会再次运行确定性 HarnessValidator；失败时 reject 本次 iteration 并可能回 Compiler。

### 7.4 翻译后的提示词与组装

#### 系统提示词

~~~markdown

你是 Compiler。把一个已验证、无 Teacher 的机制翻译成最小且正确的 Harness plugin 修改。

父 Harness 只读。只能通过文件工具编辑本次运行的 candidate workspace。终态返回 submitted candidate reference，不在终态中返回源码。

**解释规则**

- `behavioral_pseudocode` 是控制流和状态变化的权威定义。
- 其他 mechanism 字段约束能力、安全、证据和可观察性。
- 每条 `phase_rules[].decision_evaluator` 是该 phase 如何判断 trigger predicate 的权威定义；混合 evaluator 必须逐 phase 保留。
- 委托给 Actor 的工作必须成为反馈；Hook 不得替 Actor 执行。
- 伪代码与 activation budget、prohibited behavior 或可用输入冲突时，返回 `needs_revision` 并指出精确冲突。

程序提供的 Compiler context 含根据机制选择的 `capability_packet`，它是 candidate 的主要公共 API。不得发明 packet 未包含的成员。`semantic_required_capabilities` 是 Actor 行为约束，不是缺失 API。只有 `unresolved_api_capabilities` 或 `unresolved_symbols` 含实现关键 symbol 时，才用 `query_hook_api` 查询精确缺口。已在 packet 中的 symbol、重复 symbol 和超过四个唯一 symbol 的查询会被程序拒绝，且不会重新播放它们的 contract。不得把 exact query 当作通用 API discovery。若硬预算内仍无法解决必要操作，返回 `needs_revision` 并点名该操作。

POST_TOOL 机制若要向下一次 Actor generation 交付指令，应使用 `stage.tool_result` write contract：用保留原 result 且附加指令的新 ToolResult 替换当前 ToolResult；Loop 会把该 content 持久化为下一条 user-role message。不得发明 message append API 或未记录 stage key。

**流程**

1. 列出父文件并读取 `harness.json`。
2. 创建新 extension 前检查已有 mutable extensions；修改现有 mutable extension 若这是最小一致实现。只有机制依赖 fixed component 实现时才读取它；不得修改 fixed component。
3. 根据 capability packet 规划，不重复查询其中 contract。
4. 写入最小完整 component 和 manifest 更新。
5. 调用 `finalize_candidate(summary)`；程序计算 diff、运行确定性 source review/validation，并冻结精确 revision。
6. 返回 `repair_required` 时只修复报告错误并再次调用；返回 `submitted` 时输出其精确 candidate ref。

**最小 lowering 规则**

- `deterministic` rule 只能实现该 rule `decision_inputs` 上的明确可复现规则；不得加模型调用，也不得用发明的关键词、正则、分数或 heuristic 近似开放语义 predicate。
- `hook_model` rule 使用 `HookContext.call_model`、packet 的 `allowed_model_profiles` 和模型 contract。模型调用是该 rule 必需的 evaluator，不是可选增强；精确的 phase、类型、声明状态和 activation-budget guard 到达语义决策点后必须调用模型。请求只从该 rule 的 inputs 构造，显式解析声明结果，并实现 deterministic fallback。
- 不得把 `hook_model` rule 的任何语义 predicate 移入关键词、子串、正则、分数或其他自行发明的 deterministic pre-filter。围绕该 rule 的确定性代码只能检查公共 contract 提供的精确结构条件。若 implementation constraint 要求的语义 pre-filter 与声明 evaluator 冲突，返回 `needs_revision` 并指出冲突，不得静默改变机制。
- evaluator 与 trigger、伪代码、required capabilities 或证据边界冲突时返回 `needs_revision`。
- 默认由一个 extension 返回一个实现完整机制的 Hook；新多 phase 实现让该 Hook 订阅全部必需 phase。只有机制明确需要独立注册组件，或复用现有 mutable 结构严格更小时，才使用多个 Hook，并在选择前说明理由。跨 phase 状态必须使用声明的 `extension.*` 或 `shared.*` state。
- `handle` 只做 phase 路由；每个订阅 phase 的行为放在唯一私有方法 `_handle_<phase>` 中。phase handler 只实现分配给它的 rule，不再次检查 `context.phase`。单 phase Hook 的 `handle` 不做冗余 phase 判断，直接调用唯一 handler；多 phase Hook 显式分派并在调用后返回：

```python
def handle(self, context: HookContext) -> None:
    if context.phase == HookPhase.POST_TOOL:
        self._handle_post_tool(context)
        return
    if context.phase == HookPhase.PRE_FINAL:
        self._handle_pre_final(context)
        return

def _handle_post_tool(self, context: HookContext) -> None:
    ...

def _handle_pre_final(self, context: HookContext) -> None:
    ...
```

  按实际注册 phase 调整该结构。phase-handler 方法是必需的组织边界，不受“一次性 helper”禁令约束。共享一个 Hook 不得合并或重排各 phase 的 condition、action、evaluator、activation budget 或 state hand-off。
- 保留当前 accepted decision 意味着直接返回，不读取或重写。
- 一个机制状态使用一个 `StateRef`，明确 default 和 writer permission。
- one-shot boolean 通过设为 `True` 消耗，不得加 counter 或镜像状态。
- deferred feedback 直接写入，不先读取当前 decision。
- 除必需的 phase-handler 方法外，不增加一次性临时变量、只用一次 helper、dummy read、dummy `del` 或复述代码的注释。
- 多行 Actor feedback 放在一个常量中。
- 删除未使用 import 和伪代码/API contract 不需要的每一行。

**Factory 与失败策略**

- 拒绝未知 config key。若 manifest 使用空 config 且 component 无选项，factory 必须显式 `if config: raise ValueError(...)`。
- 未使用 factory context 参数保持未使用，不加 `del context/del config` 或 no-op read。
- 只捕获机制 fallback 覆盖的具体异常；不得捕获 `Exception/BaseException`。
- Hook model response parsing fallback 不表示吞掉 transport/runtime error。
- implementation constraint 明确要求 stage type validation 时，在字段访问前加对应 `isinstance`。

公共 API catalog 是白名单；不得使用 private/unqueried member、反射或 `getattr/hasattr/setattr/delattr`。fixed component 不变，新模型组件必须 mutable。

验证前确认每个 implementation constraint 已落实、每条 phase rule 已注册并执行自己的效果、`handle` 仅含 phase dispatch 且每个 phase 行为位于对应 `_handle_<phase>` 方法、每条 rule 执行其 phase-local activation budget、重复激活走该 rule 的 no-op/fallback、跨 phase read 有早先路径上的声明 write、persistent write 有匹配 `StateRef.writers`、stage write 已列入 `writable_stage_keys`、feedback 和 prompts 均无答案/案例实体/案例特定查询、phase handler 不重复检查已路由 phase，且实现无 accepted-decision rewrite、unused read 或 dummy statement。

`finalize_candidate` 只证明 deterministic source review、manifest、import 和 Hook contract legality，不证明真实轨迹行为。写代码前完成语义审计；程序执行机械审计时不会把已成功文件或 diff 回放进模型上下文。只有 mechanism 本身不足时才返回 `needs_revision`；普通 validation error 必须在本次运行修复。

~~~

#### 用户提示词

~~~markdown

角色输入：

```text
{{role_input}}
```

程序提供的资源上下文：

```text
{{resource_context}}
```

把给定 mechanism 编译成一个已验证内存 candidate，或指出阻止安全实现的最窄缺失规格。

~~~

#### 本角色组装补充

- `resource_context["compiler"]` 包含 `parent_plugins_root`、parent digest、Harness ID、fixed components、`file_count`、查询预算和 source-derived capability packet。
- 同一实际 user prompt 顶层还含 `evaluation=null`、`trials=null`、`intervention=null`、`candidate_review=null`，以及 `mechanisms={"draft_count": 0, "validated_count": 0}`；这些空资源键由通用 `model_context()` 固定组装。
- 每次 Compiler 调用创建新的内存 CandidateWorkspace；Controller revision 通过约束和 validation feedback 重新调用，而不是恢复同一 Compiler transcript。
- 输出终态工具名为 `submit_compiler_result`。

### 7.5 可调用工具

```python
def list_harness_files() -> ToolResult:
    """List the current in-memory candidate Harness files."""

def read_harness_file(path: str) -> ToolResult:
    """Read one UTF-8 file from the in-memory candidate Harness."""

def query_hook_api(symbol: str) -> ToolResult:
    """Resolve one packet gap under the Compiler's hard query budget."""

def write_candidate_file(path: str, content: str) -> ToolResult:
    """Create or replace one mutable file in the candidate workspace."""

def delete_candidate_file(path: str) -> ToolResult:
    """Delete one mutable file from the candidate workspace."""

def finalize_candidate(summary: str) -> ToolResult:
    """Validate and freeze the current revision, or return repair errors."""

def submit_compiler_result(
    *,
    decision: CompilerDecision,
    candidate_ref: str | None = None,
    implementation_summary: str,
    unresolved_risk: str | None = None,
) -> ToolResult:
    """提交并校验最终 compiler_result@1；由运行时自动注入。"""
```

注意：`builtin_tools.py` 还实现了 `get_hook_authoring_guide`、`list_hook_api_symbols`、`show_candidate_diff`、`validate_candidate` 和 `submit_candidate`，但当前 Compiler manifest **没有注册**它们，因此本角色当前不可调用。

### 7.6 代码上的额外机制

- `query_hook_api` 最多允许四个 unique symbols；packet 已含 symbol、重复 symbol 和超预算查询均被拒绝。
- candidate 只存在内存 overlay，`finalize_candidate` 校验通过后冻结 exact revision/digest。
- fixed component 的 manifest 或目录文件不可修改；新 component 必须标记 `mutable`。
- deterministic source review 禁止动态 attribute builtins，并检查常见 Hook authoring policy。
- HarnessValidator 会装配 candidate，并对每个注册 Hook 的每个订阅 phase 使用代表性非空 trace 做 contract smoke test。
- Compiler `needs_revision` 的 `implementation_summary` 被上游解释为“mechanism/capability 约束”，而不是普通代码修复说明。
- **ref—artifact 对齐缺口**：终态校验只用 `resolve(output.candidate_ref)` 确认该 ref 是本次 run 中任一已提交 candidate；但 `CompilerWorkspaceStore.artifact()` 始终返回序号最大的最后一次 submitted candidate。若一次 run 成功 finalize 多次后提交旧 ref，输出校验仍通过，而持久化 artifact 与后续 Stage 使用的是最新 candidate，可能和 `candidate_ref` 不一致。
- stage 发现相同 parent/digest 的已拒绝 iteration 时会复用其 validation failure，不重新提交重复 candidate。

---

## 8. Conformance Reviewer（`conformance_reviewer`）

### 8.1 关系图位置

#### 路由至当前角色

- `[确定性 Candidate Stage/Validation]`：`STAGE_CANDIDATE` 返回 `outcome["status"] == "valid"` 时，Controller 创建 `VERIFY_CONFORMANCE`。
- `[Candidate rollout]`：`VERIFY_CONFORMANCE` 对每个干预 example 固定运行 `CONFORMANCE_REPLICATES == 3` 条 Candidate rollouts。某条 record 不含 `runner_error` 时，为该 record 调用一个独立 Conformance Reviewer。
- `[确定性 runtime-error finding]`：record 含 `runner_error` 或缺少预期 replicate 时，不调用该角色，程序直接构造 `verdict="runtime_error"` 的 ConformanceFinding。

#### 从当前角色路由出去

单个 Conformance Reviewer 不直接路由。全部 findings 经 `aggregate_conformance()` 聚合后：

- `[Candidate Evaluation]`：`summary.decision == "pass"` 时。
- `[确定性 Reject Candidate]`：`summary.decision == "revise_implementation"` 时；若增加后的 `candidate_revision <= config.max_candidate_revisions`，Reject 完成后再路由 Compiler，否则 Reject 后终止。
- `[Controller 重试/暂停]`：`VERIFY_CONFORMANCE` effect 抛异常时，若 `item.attempt <= config.max_work_retries` 则重试整个 effect（不是只重试单条 finding）；否则按 failure budget 暂停。

### 8.2 输入协议

```python
class ConformanceReviewerInput(TeacherPayload):
    mechanism: MechanismSpec
    # Candidate 应忠实实现的完整机制规格。

    trial_refs: list[str] = Field(min_length=1)
    # 当前 example 对应的原 Intervention trials。

    reference_observations: list[dict[str, Any]] = Field(min_length=1)
    # 从原 trials 提取的 phase plan、activation、change 和 effect 事实。

    example_id: str = Field(min_length=1)
    # 当前 Candidate replay 的逻辑样本 ID。

    replicate_id: str = Field(min_length=1)
    # 当前 Candidate replay 的 replicate ID。

    candidate_trajectory: dict[str, Any]
    # 当前完整 Candidate Actor rollout 的 conformance 投影。
```

每个 example 的输入只包含与该 example 原 trial 对应的 reference observations。

### 8.3 输出协议

```python
ConformanceVerdict = Literal[
    "faithful",
    "implementation_mismatch",
    "not_observed",
    "runtime_error",
    "inconclusive",
]

class ConformanceFinding(TeacherPayload):
    trial_refs: list[str] = Field(min_length=1)
    # 必须原样复制当前输入中的原 trial refs。

    candidate_run_ref: str = Field(min_length=1)
    # 必须为 `<example_id>/<replicate_id>`。

    verdict: ConformanceVerdict
    # 单条 Candidate rollout 的机制实现保真结论。

    observed_phases: list[HookPhaseName] = Field(default_factory=list)
    # 实际观察到 Candidate 机制的 MechanismSpec 声明 phases。

    assessment: str = Field(min_length=1, max_length=1200)
    # 只针对实现保真的事实判断。

    repair_obligation: str | None = Field(default=None, max_length=500)
    # 非 faithful verdict 时的通用实现修复义务。
```

允许取值与约束：

- `verdict` 只允许上述五值。
- `observed_phases` 不得重复。
- `faithful` 必须至少有一个 `observed_phases`，且 `repair_obligation` 必须为空。
- 其他四种 verdict 必须有非空 `repair_obligation`。

后处理：

1. `candidate_run_ref` 必须精确等于当前输入的 `example_id/replicate_id`。
2. 输出 `trial_refs` 必须与输入列表完全相等。
3. `observed_phases` 中不属于 MechanismSpec 的 phase 会被 effect 移除。
4. 若原 verdict 为 `faithful`，移除无关 phase 后列表为空，程序把 finding 改为 `inconclusive`，并写入固定 assessment/repair obligation。
5. 每个 intervention example 必须恰有 r000/r001/r002 三条 finding。
6. 任意 `runtime_error` 或 `implementation_mismatch` 都使 aggregate decision 为 `revise_implementation`。
7. 即使没有 hard failure，每个 example 也必须至少一条 `faithful`；否则为 `revise_implementation`。
8. 只有无 hard failure 且每个 example 至少一条 faithful 时为 `pass`。

### 8.4 翻译后的提示词与组装

#### 系统提示词

~~~markdown

你是 Conformance Reviewer。只检查一条完整 Candidate Actor rollout，判断编译后 Harness 是否忠实实现给定 MechanismSpec。

这是实现一致性审查，不是答案质量审查：

- `faithful`：相关 phase 已到达，声明 inputs 控制了 decision，phase action 和状态转换符合机制，activation budget/fallback 得到遵守，Actor 收到对应控制或上下文效果。
- `implementation_mismatch`：轨迹显示与机制矛盾的行为，包括错误 phase、错误 action、错误 state lifetime、重复激活、缺失 Actor feedback 或 prohibited behavior。
- `not_observed`：完整 rollout 从未出现适用机制激活。
- `runtime_error`：Candidate 因编译 Harness 执行失败。
- `inconclusive`：轨迹接近相关行为，但记录不足以确认实现是否忠实。

不得以答案正确性作为实现保真证据。faithful rollout 可以答错，mismatched rollout 可以答对。

所有非 faithful verdict 必须给出一个实现层 repair obligation，内容必须通用，不含问题、golden answer、案例实体、案例查询或复制轨迹文本。faithful 时 `repair_obligation` 为空。

在 POST_TOOL，Loop 会把最终 ToolResult content 作为下一条 user-role conversation message。因此保留原 tool result 并把机制指令附加到 content，符合“append user-role message”动作；当完整指令在下一次 model input 可见时，不得要求单独 message object 或未记录 context append API。

`candidate_run_ref` 精确设为输入中的 `<example_id>/<replicate_id>`，只复制输入提供的 `trial_refs`。

`observed_phases` 只报告 MechanismSpec 声明且实际观察到 Candidate mechanism 的 phase；不得加入 baseline component 的无关 phase。若未观察任何声明 phase，返回空列表并使用 `not_observed` 或 `inconclusive`。

~~~

#### 用户提示词

~~~markdown

角色输入：

```text
{{role_input}}
```

程序提供的资源上下文：

```text
{{resource_context}}
```

只检查当前 Candidate rollout 并提交一条 conformance finding。

~~~

#### 本角色组装补充

- `resource_config` 为空，因此 `resource_context` 精确包含 `evaluation/trials/intervention/compiler/candidate_review = null`，以及空的 mechanism draft 计数摘要；全部实质审查材料直接包含在 role input。
- 每条 replay 使用一个新的独立 Teacher 会话；并发数受 `judge_workers` semaphore 限制。
- 输出终态工具名为 `submit_conformance_finding`。

### 8.5 可调用工具

该角色没有业务工具，只有终态工具：

```python
def submit_conformance_finding(
    trial_refs: list[str],
    candidate_run_ref: str,
    verdict: ConformanceVerdict,
    observed_phases: list[HookPhaseName],
    assessment: str,
    repair_obligation: str | None = None,
) -> ToolResult:
    """提交并校验最终 conformance_finding@1；由运行时自动注入。"""
```

### 8.6 代码上的额外机制

- Candidate conformance replay 只覆盖曾用于 Intervention trials 的不同 example，而非整个 Experience Set。
- 每个 example 固定执行 3 个 Candidate replicates。
- runner error 不交给模型判断，程序直接生成 runtime_error finding。
- aggregate gate 允许同一 example 三条中只有一条 faithful，只要没有任何 hard failure。
- `not_observed/inconclusive` 本身不是全局 hard failure；但某 example 三条均无 faithful 时仍阻止通过。
- Conformance pass 只证明实现与机制一致，不证明任务收益；通过后仍需完整 Candidate Evaluation 和 Candidate Reviewer。
- **持久化差异**：effect 会清洗本地 `finding.observed_phases`，必要时把 `faithful` 改成 `inconclusive`，aggregate 使用的是清洗后对象；但当前写入单 finding JSON 时仍写原始 `artifact`，没有把修正后的 `finding` 回写到 `artifact["output"]`。因此单 finding artifact 与 aggregate 实际输入可能不一致。

---

## 9. Candidate Reviewer（`candidate_reviewer`）

### 9.1 关系图位置

#### 路由至当前角色

- `[Candidate Evaluation]`：`EVALUATE_CANDIDATE` effect 成功完成时，无指标值分支，Controller 把 `candidate_metrics` 写入 payload 并固定创建 `REVIEW_CANDIDATE`。
- 由于 Candidate Evaluation 仅在 `conformance_summary.decision == "pass"` 后发生，所以当前角色总是位于 conformance gate 之后。

#### 从当前角色路由出去

Controller 先计算 `gate = evaluate_promotion(...)`：

- `[Promote Candidate]`：`gate.passed is True` 时。该值等价于：
  - `validation_summary["passed"] is True`；
  - candidate runner error count 可用且等于 0；
  - incumbent/candidate accuracy 均可用；
  - `accuracy_delta >= config.min_accuracy_delta`；
  - 若配置 `max_total_token_ratio`，token 数据有效且 ratio 不超过阈值；
  - `output["recommendation"] == "accept"`。
- `[Reject Candidate → Trial Selector]`：`gate.passed is False`、`output["recommendation"] == "revise"`、`output["revision_target"] == "evidence"`、增加后的 `candidate_revision <= config.max_candidate_revisions`，并且 `trial_count < config.max_trials_per_hypothesis` 且 `assignment_count < config.max_trial_assignments`；Reject 完成后进入 Trial Selector。
- `[Reject Candidate → Mechanism Distiller]`：同上但 `revision_target == "mechanism"`。
- `[Reject Candidate → Compiler]`：同上但 `revision_target == "implementation"`。
- `[Reject Candidate → 流程终止]`：`gate.passed is False` 且 recommendation 不是 `revise`，或 candidate revision budget 已耗尽。
- `[Reject Candidate → 流程终止]`：上述 evidence revision 已通过 candidate revision budget，但 `trial_count >= config.max_trials_per_hypothesis` 或 `assignment_count >= config.max_trial_assignments` 时，不再进入 Trial Selector。
- `[Controller 重试/暂停]`：`REVIEW_CANDIDATE` effect 抛异常时，若 `item.attempt <= config.max_work_retries` 则重试同一 work；否则按 failure budget 暂停。

### 9.2 输入协议

```python
class CandidateReviewerInput(TeacherPayload):
    mechanism: MechanismSpec
    # Candidate 应实现且已通过 conformance replay 的机制目标。

    validation_summary: dict[str, Any]
    # Compiler validation、conformance、incumbent/candidate metrics 的组合摘要。

    implementation_summary: str = Field(min_length=1)
    # Compiler 对当前 Candidate 实现的说明。

    unresolved_risk: str | None = None
    # Compiler 声明仍存在的风险。

    historical_experience: list[str] = Field(default_factory=list)
    # 供 Reviewer 参考的历史经验；当前 Controller 固定传空列表。
```

`validation_summary` 当前结构：

```python
{
    "compiler_validation": work.payload["validation_summary"],
    "mechanism_conformance": compact_conformance_summary,
    "incumbent_metrics": work.payload["incumbent_metrics"],
    "candidate_metrics": work.payload["candidate_metrics"],
}
```

### 9.3 输出协议

```python
CandidateRecommendation = Literal["accept", "revise", "reject"]

class CandidateReview(TeacherPayload):
    recommendation: CandidateRecommendation
    # 对当前 Candidate 的局部 promotion 建议。

    observed_effect: str = Field(min_length=1)
    # 对已观察收益、损失、稳定性和成本变化的独立描述。

    reason: str = Field(min_length=1)
    # 给出该 recommendation 的理由。

    next_obligation: str | None = None
    # `revise` 时下一项具体、可测试义务。

    revision_target: Literal[
        "evidence", "mechanism", "implementation",
    ] | None = None
    # `revise` 时义务应回到的层级。
```

允许取值与约束：

- `recommendation` 只允许 `accept/revise/reject`。
- `revise` 时 `next_obligation` 与 `revision_target` 均必填。
- `accept/reject` 时两者都必须为空。

后处理：

1. Candidate Reviewer 提交前必须至少调用一次 `get_paired_actor_trajectory`。
2. 若比较集中存在 improved case，至少检查一个 improved case 的 paired trajectory。
3. 若存在 regressed case，至少检查一个 regressed case 的 paired trajectory。
4. effect 再次校验输出并写入 `candidate_reviewer_artifact`。
5. Reviewer recommendation 不是最终决定；Controller 把它与确定性 safety gate 合并。
6. `revise` 只有在 gate 未通过时才进入 revision 分支；recommendation 为 `accept` 但 safety gate 失败会直接 Reject，不会自动修订。

### 9.4 翻译后的提示词与组装

#### 系统提示词

~~~markdown

你是 Candidate Reviewer。你负责使用成对 incumbent/candidate 证据，判断一个编译 candidate 应被 promote、revise 还是 reject。Controller 另外执行确定性安全要求，包括 validation、runner errors、指标可用性、严重 accuracy regression 和过高 token cost。

角色输入中的确定性 validation 是权威信息。使用以下全部内容判断 observed effect：

- 数值 Mechanism Conformance Replay 摘要；它证明实现保真，不证明任务收益；
- aggregate accuracy 和逐 example 稳定性变化；
- 机制及其引用证据针对的 failure cases；
- gain/loss 数量，以及条件允许时两组代表性 paired trajectories；
- token usage 和其他执行成本变化；
- Harness diff 是否真的实现给定机制。

不得隐式使用 `accuracy_delta >= 0` 规则。轻微总体回归只有在具体 target-case 与稳定性收益超过损失且仍在 Controller safety floor 内时才可接受；正 delta 也不足以接受未观察、脆弱或成本不成比例的机制。

建议规则：

- `accept`：预期机制已观察，且收益、稳定性、适用性、回归和成本共同支持采用；
- `revise`：机制有希望，但仍有一个有界实现或证据 obligation；
- `reject`：candidate 无效、无效果、有害或与机制冲突。

你只建议 promotion，不修改版本。`observed_effect` 与 `reason` 分开。`revise` 时 `next_obligation` 必须具体可测试，且 `revision_target` 精确为：

- `evidence`：需要另一 intervention trial 或证据判断；
- `mechanism`：实现无关机制必须改变；
- `implementation`：只有编译 Harness transaction 必须改变。

`accept/reject` 时 `next_obligation` 与 `revision_target` 均为空。

~~~

#### 用户提示词

~~~markdown

角色输入：

```text
{{role_input}}
```

程序提供的资源上下文：

```text
{{resource_context}}
```

检查成对 outcome changes 和充分轨迹/代码证据，然后提交一个局部 promotion recommendation。

~~~

#### 本角色组装补充

- `resource_context["candidate_review"]` 提供 example 数量、incumbent/candidate metrics、paired change counts 和 diff 可用性。
- 同一实际 user prompt 顶层还含 `evaluation=null`、`trials=null`、`intervention=null`、`compiler=null`，以及 `mechanisms={"draft_count": 0, "validated_count": 0}`。
- Reviewer 运行期间，pending iteration 被 stage 成只读 Candidate plugins root，用于 diff。
- 输出终态工具名为 `submit_candidate_review`。

### 9.5 可调用工具

```python
def list_candidate_changes(
    page: int = 1,
    page_size: int = 10,
    change: Literal["any", "improved", "regressed", "unchanged"] = "any",
) -> ToolResult:
    """List paired incumbent/candidate outcome changes."""

def get_candidate_case(example_id: str) -> ToolResult:
    """Read paired evaluation details for one logical example."""

def get_paired_actor_trajectory(
    example_id: str,
    replicate_id: str,
) -> ToolResult:
    """Read paired Actor trajectories for one example replicate."""

def get_candidate_harness_diff() -> ToolResult:
    """Read the candidate Harness file diff when roots were configured."""

def submit_candidate_review(
    recommendation: CandidateRecommendation,
    observed_effect: str,
    reason: str,
    next_obligation: str | None = None,
    revision_target: Literal[
        "evidence", "mechanism", "implementation",
    ] | None = None,
) -> ToolResult:
    """提交并校验最终 candidate_review@2；由运行时自动注入。"""
```

### 9.6 代码上的额外机制

- 成对报告必须具有相同 example ID 集合，否则 CandidateComparisonStore 构造失败。
- 提交门槛要求至少检查一条 paired trajectory，并分别覆盖存在的 improved/regressed 类别。
- 程序不强制调用 `list_candidate_changes`、`get_candidate_case` 或 `get_candidate_harness_diff`；尤其提示词虽要求检查 code evidence，runtime 没有“必须读取 diff”的 gate。
- promotion safety gate 检查的是 Compiler validation summary、runner errors、accuracy floor 和 token ratio；conformance 已在更早阶段 gate，但其摘要仍提供给 Reviewer。
- `effect_passed` 仅等于 `recommendation == "accept"`；Reviewer 的 reason 不参与程序化 gate。
- Reviewer `accept` 不能覆盖 safety failure，Reviewer `reject` 也不能被正指标覆盖。
- Promote effect 通过 Version Store `session.accept()` 做最终 validation 与 Git commit；Reviewer 本身无版本写权限。

---

## 10. 跨角色审核时应特别关注的实现事实

1. **角色数量注释过时**：`LocalControlEffects` docstring 写“eight v2 roles”，但协议 registry 和实际 effect 已接入 9 个角色，新增/额外的是 Conformance Reviewer。
2. **Worker 的 unsupported 分支当前不可达**：协议和 transitions 都支持 `unsupported_hypothesis`，当前正式 `_worker_result()` 只生成 `executed/unsuitable_assignment`。
3. **Evidence Reviewer continuation 未接入正式 Controller**：runtime 实现了 `continue_reviewer()`，但 `REVIEW_EVIDENCE` effect 每次调用全新 `runtime.run()`。
4. **Evidence Reviewer 的 reject 不是终止**：程序把 `revise/reject` 都路由回 Hypothesis Researcher，差别只存在于反馈内容。
5. **Failure Analyst 无“无方向”结果**：新协议要求始终提交一个 FailureDirection；旧 Critic 的 no direction 正常终态不再存在。
6. **Compiler revision reason 复用 implementation_summary**：`needs_revision` 没有专门 reason 字段，Controller 把 `implementation_summary` 当作 capability constraint。
7. **Conformance 是 stochastic-one-of-three gate**：每个 example 三个 replay 中至少一个 faithful 即可，但任何一条 runtime_error/implementation_mismatch 都会整体失败。
8. **Candidate Reviewer accept 不是最终 accept**：只有 `recommendation == "accept"` 且全部 deterministic safety 条件通过才会 Promote。
9. **当前演化对象是 Harness 文件事务**：没有 Student 权重更新；fixed parent components 受 Validator 保护，新模型生成组件必须 mutable。

## 11. 主要代码依据索引

- 角色输入/输出协议与 registry：`search_harness/teacher/contracts.py`
- 普通 Teacher 原生工具循环、终态提交和 continuation：`search_harness/teacher/native_runtime.py`
- Intervention Worker 专用角色运行时：`search_harness/teacher/intervention_runtime.py`
- Intervention Worker activation 工具：`search_harness/adapter/intervention/worker.py`
- Teacher 资源绑定与角色终态资源校验：`search_harness/teacher/resources.py`
- Compiler/Candidate Reviewer 角色资源：`search_harness/teacher/role_resources.py`
- 显式 Teacher 工具定义：`search_harness/teacher/builtin_tools.py`
- 正式 Controller work 类型：`search_harness/evolution/control/domain.py`
- 精确状态路由：`search_harness/evolution/control/transitions.py`
- 角色输入构造与 effect 后处理：`search_harness/evolution/control/effects.py`
- promotion safety/effect gate：`search_harness/evolution/control/policies.py`
- conformance 三 replicate 聚合：`search_harness/evolution/conformance.py`
- Candidate 固定边界、装配和 Hook contract 校验：`search_harness/versioning/validation.py`
- 各角色英文 prompt 源：`harness_templates/teacher/<role>/plugins/prompts/<role>/templates/`
