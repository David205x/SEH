# Teacher Runtime

## 目的

Teacher Runtime 为 Teacher 角色提供独立于 Actor `agent_loop` 的执行环境。它从类似 Harness template 的目录加载 Prompt 和 Tool，并默认通过 OpenAI-compatible Chat Completions 直接执行 provider-native tool calling。

当前实现八个可独立运行的角色：

- `failure_analyst`
- `hypothesis_researcher`
- `trial_reviewer`
- `evidence_reviewer`
- `mechanism_distiller`
- `intervention_worker`
- `compiler`
- `candidate_reviewer`

这些角色既可独立运行，也已由
[Evolution Controller](evolution-controller.md) 装配为正式闭环。一个角色的
结构化输出由调用程序校验后写入 artifact，再由确定性局部转移选择后续工作。

## 分层

Teacher 角色由三个层次组成：

1. **Template**：`harness_templates/teacher/<role>/plugins/` 保存可配置的 Prompt、Tool 清单和 manifest。
2. **Neutral spec**：loader 把目录解析为 `TeacherAgentSpec`，不依赖具体 Agent SDK。
3. **Runtime adapter**：默认的 `NativeChatTeacherRuntime` 将 spec 转为原生 `messages + tools` 请求；可选的 `AgentsSdkTeacherRuntime` 用于 SDK 对照实验。

`harness.json` 引用角色及输出协议，而不嵌入 Python 类：

```json
{
  "schema_version": 1,
  "harness_id": "teacher_failure_analyst_v1",
  "role": {"id": "failure_analyst", "version": 1},
  "output_contract": {"id": "failure_direction", "version": 1},
  "tools": [],
  "prompt": {}
}
```

代码内 registry 将 `role.id + version` 绑定到输入 Pydantic 类型，并将 `output_contract.id + version` 绑定到输出 Pydantic 类型。加载时会校验二者匹配，防止 template 任意替换角色协议。

## 消息角色

- Template 的固定职责、约束和工具使用规则以 `system` 消息输入。
- 当前任务的角色输入、上游角色产物和程序资源摘要以 `user` 消息输入。
- 工具执行结果使用原生 `tool` 消息；assistant 的 tool call 保持原生结构。
- Researcher 或 Reviewer continuation 的外部反馈追加为新的 `user` 消息，
  不改写既有 system prompt。

## Native 工具循环

默认使用 `NativeChatTeacherRuntime`。Runtime 根据输出 Pydantic schema 动态增加终止工具 `submit_<contract_id>`；模型通过原生工具调用提交结果，Runtime 再进行 Pydantic 校验。DeepSeek 的普通 Tool Calls 端点支持这一交互方式。

如果提交满足 JSON schema 但违反 Pydantic 跨字段语义，Runtime 会把校验错误作为工具结果送回同一对话，并允许模型重新提交；只有通过完整校验的 submit 调用才会终止角色运行。

原生循环显式维护 assistant `tool_calls` 与对应的 `role=tool` 消息，不依赖 `<tool_use>` 等文本标签，也不复用 Actor `agent_loop`。无工具自由文本、非法 JSON 参数、未知工具和终态协议错误都会成为模型可见反馈；确定性的最大 turn 预算由 Runtime 维护。

Runtime 请求 provider 不并行调用工具；如果 provider 仍在一次回复中返回多个普通工具调用，Runtime 会按返回顺序串行执行并逐一回填结果。终态 submit 工具必须单独调用，避免同一轮同时修改证据状态并提交结论。

可选的 `AgentsSdkTeacherRuntime` 仍可用于后端对照。其 Pydantic `output_type` 会生成 `response_format.type=json_schema`；DeepSeek JSON Output 提供的是 `response_format.type=json_object`，二者不是同一协议。因此当前 CLI 不使用 SDK structured output。

DeepSeek `json_object` 模式还要求 Prompt 明确出现 `json` 并提供目标 JSON 示例，同时仍可能返回空 content。若未来增加该模式，应将它实现为独立 provider adapter，并为截断、空 content 和 Pydantic 二次校验设置统一重试，而不是把它等同于 SDK native structured output。

DeepSeek 的 Tool Calls `strict` 模式属于 Beta 能力，需要 `/beta` base URL，并只支持文档列出的 JSON Schema 子集。当前 Pydantic schema 含有 `minLength`、`minItems` 等 Beta strict 不支持的关键字，因此 Runtime 不依赖 DeepSeek 服务端 strict 保证；最终合法性始终由本地 Pydantic 校验确定。

对于较大的结构化产物，模型先通过窄工具逐步构造，最终只提交决策和产物引用。例如 Mechanism Distiller 必须依次创建、补全并校验机制草稿，最终返回 `mechanism_ref`。

## 资源

Request 文件包含：

```json
{
  "input": {},
  "resources": {
    "report_dir": "...",
    "rollout_file": "...",
    "actor_plugins_root": "...",
    "trial_files": [],
    "intervention": null,
    "compiler": null,
    "candidate_review": null
  }
}
```

- `input` 必须满足当前角色的 Pydantic 输入协议。
- `resources` 只声明本次允许访问的显式资源，不允许角色任意扫描实验目录。
- 相对资源路径以 request 文件所在目录为基准；需要引用仓库其他位置时可使用绝对路径。
- evaluation case 使用 `example_id` 定位概要，轨迹使用 `example_id + replicate_id` 精确定位。
- 文本文件统一按 UTF-8 读取；CLI 允许带 UTF-8 BOM 的 Windows request 文件。
- `intervention` 显式指定源 rollout、Actor plugins 和 Student 预算。只有
  专用 `InterventionRoleRuntime` 会读取 `STUDENT_*`，从一个 inclusive
  prefix 启动由同一 Teacher Worker transcript 控制的多 phase Student 分支。
- `compiler` 指定只读 Parent Harness。Compiler 只能通过内存 workspace 工具修改候选，校验通过后获得本次 run 内的 `candidate_ref`。
- `candidate_review` 指定 incumbent/candidate 的成对 report、rollout 及可选 Harness roots。Reviewer 必须检查至少一组成对轨迹后才能提交建议。

资源进入 Prompt 前按角色投影，而不是统一注入完整总览：

- Failure Analyst 只收到结果与执行摘要；token 分布通过
  `get_cost_summary` 按需读取，并可用 `list_evaluation_cases_by_cost`
  按 replicate 均值定位高成本案例。
- Hypothesis Researcher 只收到引用规模和 Actor 组件 ID。它只能读取
  Analyst 在 `evidence_refs` 中列出的行为轨迹，且看不到 golden answer
  或完整视图；必须读取全部引用轨迹及 `get_intervention_capabilities`
  后才能提交。修订回合可按显式 `trial_files` 追加 Reviewer 已审 trial，
  并通过 `get_trial_evidence` 按需读取事实轨迹。
- Trial Reviewer 的 `get_trial_evidence` 返回 source/branch 两侧完整
  run 和 trace，保留 model input、native reasoning、动作、结果和 Hook
  事件，只删除模型 `usage`、源文件路径和模型 provenance 等非判断元数据。
  工具还会过滤旧 Worker artifact 的自然语言 summary。Evidence Reviewer
  不读取轨迹工具，只接收独立 TrialReview 和确定性聚合观察。
- 其他角色暂时沿用通用资源总览，后续按相同原则逐一收窄。

## 独立运行

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe `
  -m search_harness.teacher `
  --template_root harness_templates\teacher\failure_analyst\plugins `
  --request_file path\to\request.json `
  --output-file runs\components\teacher\failure_analyst.json `
  --env-file .env `
  --max-turns 15
```

通用 Teacher Runtime 默认只读取 `TEACHER_*` 模型配置。Intervention Worker
是唯一使用专用 runtime 的角色：程序验证 `prefix_id/fork_phase`、重建
inclusive prefix，并在同一 Student continuation 到达每个配置 phase 时恢复
同一个 Teacher Worker 对象。每次激活只执行一个终止 action，phase 预算相互
独立；Teacher 与 Student provenance、Worker transcript、phase 激活/修改和
完整 Actor 轨迹统一记录在一个 artifact 中。

运行 artifact 保存输入、资源声明、结构化输出、工具调用、token usage、完整结构化消息 transcript 和具体 runtime 名称。工具产生的大对象保存在 `resource_artifacts`：当前包括完整 intervention trial 和已提交 Compiler candidate，模型终态只保留窄语义结果或引用。

每个通用 Native run 还保存 `role_session`：

- `session_id` 与单调递增的 `revision`；
- 已读取 Actor 轨迹、Intervention trial 和能力目录的程序访问账本；
- 每一版已验证结构化输出；
- Reviewer 的原始结构化反馈历史。

Intervention Worker 不使用通用 `role_session`。它的跨 phase 连续性保存在
`worker_trace` 及同一个 Worker 内部消息历史中，并只在当前 trial 生命周期内
存在；不同 trial 之间不会共享 Teacher 上下文。

`continue_researcher` 会校验模板和冻结输入，恢复完整 assistant/tool
transcript 和访问账本，然后追加一条带来源标识的 user feedback。资源配置
只允许追加显式 trial 文件，其他资源不得变化。`continue_reviewer` 可在
同一全局 Reviewer transcript 中追加已经独立生成的 TrialReview；正式
Controller 默认使用全部局部审阅重新执行一次全局判断。

常见的可恢复错误不会直接终止角色运行。非法工具参数、缺失的可选资源、未知引用和终态语义校验错误会作为 tool message 返回模型，允许其在 turn 预算内补证或修正。网络故障等外部执行错误仍由调用方处理。

## 当前边界

- Intervention Worker 的 prefix 重建、Hook bridge、跨 phase transcript 和 branch
  trial 位于 `search_harness.teacher._intervention`，属于 Teacher 私有实现，不是
  公共兼容接口。
- Teacher Judge 尚未迁移到该 Runtime。
- Compiler 当前门禁包括 manifest、fixed 边界、Python 语法、禁止动态属性探测、Harness 装配和 Hook 合约检查；standalone v2 尚未执行数据集 rollout。
- Candidate Reviewer 输出 promotion 建议，但不接受、拒绝或写入 Harness checkpoint。
- Experience Store、统一重试策略和完整状态机不属于当前独立角色实现。
- 工具结果会随结构化消息在后续 turn 中回放；当前尚未实现工具结果删除、
  micro-compact 或 transcript 摘要。

Compiler 的内存事务、源码驱动 Hook API 查询和完整工具定义见
[Compiler](compiler.md)。

## Research Revision Cycle

独立闭环入口：

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe `
  -m search_harness.teacher.research_cycle `
  --researcher-artifact runs\components\teacher\researcher.json `
  --run-dir runs\components\teacher\research_cycle_01 `
  --rollout-file runs\experiments\evolution\exp_05\iterations\0001\incumbent_rollouts.jsonl `
  --actor-plugins-root harness_templates\actor\baseline\plugins `
  --example-id <example_id> `
  --replicate-id r000 `
  --prefix-id 5 `
  --trial-objective "Test the frozen hypothesis at this prefix." `
  --env-file .env
```

单个 assignment 参数保持可用。多 trial 运行可改用
`--assignments-file path\to\assignments.json`，文件内容为
`InterventionAssignment` 对象的 JSON 数组。

该入口执行冻结假设上的一个或多个 assignment：

```text
Researcher artifact
→ Intervention Worker trial 1
→ Trial Reviewer 1
→ [more assignments] Intervention Worker trial N → Trial Reviewer N
→ Evidence Reviewer aggregate review
→ optional Researcher revision
```

Worker artifact、Trial Reviewer artifact、Evidence Reviewer artifact、
Researcher revision 和 `cycle.json` 分别
持久化在 `run-dir`。`continue` 保持假设冻结并消耗下一个 assignment；
`revise/reject` 才把 Reviewer 原始输出和已审 trial 返回同一 Researcher
session。
