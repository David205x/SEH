# Teacher Roles 查询工具审计

## 1. 范围与读取口径

本文按当前正式 Teacher Template 和 Intervention Runtime，整理模型实际可见的查询类工具。查询类包括只读检索、按需展开和诊断性探测；不包括终态提交、Candidate 文件写入、Mechanism Draft 编辑和 Intervention 动作工具。`probe_mechanism_evaluators` 会真实调用 Hook model 并产生费用，不是纯只读操作，但因其职责是返回诊断信息，仍列在查询类工具中并单独标明。

普通 Teacher 工具的参数通过 API 原生 structured tool calling 传入；返回值统一是 `ToolResult.content` 中的一行 JSON 文本，而不是 Provider 原生结构化对象。下文 JSON 使用结构示意，`null` 表示字段可能为空，`...` 表示由已注明类型定义的开放内容。

当前结论：多数目录和按需读取工具边界清楚；最明显的问题是 Candidate Reviewer 的 `get_paired_student_trajectory` 直接并排返回两份接近原始的 Rollout，绕过了已有 behavior/conformance 轨迹投影。其次是 Intervention Executor 的 `inspect_active_observation` 与 activation user message 完全重复，以及 `query_hook_api` 同时返回同一契约的结构化与 Python-native 两种表达。

## 2. Failure Analyst

### 2.1 工具签名与用途

| 工具签名 | 用途 |
| --- | --- |
| `list_evaluation_cases(page: int = 1, page_size: int = 10, stability: Literal["any", "stable_failure", "unstable", "stable_correct", "unresolved"] = "any")` | 分页列出逻辑样本的稳定性和可用 replicate，不加载轨迹。 |
| `list_evaluation_cases_by_cost(page: int = 1, page_size: int = 10, stability: ... = "any", token_metric: Literal["input_tokens", "output_tokens", "total_tokens", "student_total_tokens", "hook_total_tokens"] = "total_tokens", order: Literal["descending", "ascending"] = "descending")` | 按每题 replicate token 均值分页排序样本。 |
| `get_cost_summary()` | 返回 Evaluation 中 replicate 级 token 覆盖和分布统计。 |
| `get_evaluation_case(example_id: str)` | 返回一个逻辑样本的完整 per-example Evaluation 记录和 replicate 目录。 |
| `get_student_trajectory(example_id: str, replicate_id: str, view: Literal["behavior", "full"] = "behavior")` | 按 behavior 或完整诊断视图读取一条 Student trajectory。 |
| `get_harness_manifest()` | 返回当前 Student Template 的原始 `harness.json`。 |

> `FUTURE`：`get_harness_manifest`没有指定版本啊，未来实现多轮generation后或许可以考虑可读取指定版本的

### 2.2 返回结构

`list_evaluation_cases`：

```json
{
  "page": 1,
  "page_size": 10,
  "total_items": 75,
  "total_pages": 8,
  "items": [{
    "example_id": "...",
    "question": "...",
    "stability": "stable_failure|unstable|stable_correct|unresolved",
    "success_rate": 0.0,
    "answer_consistency": 1.0,
    "run_status": "...",
    "available_replicates": ["r000", "r001", "r002"]
  }]
}
```

`list_evaluation_cases_by_cost`：

```json
{
  "token_metric": "total_tokens",
  "order": "descending",
  "page": 1,
  "page_size": 10,
  "total_items": 75,
  "total_pages": 8,
  "items": [{
    "example_id": "...",
    "question": "...",
    "stability": "...",
    "success_rate": 0.0,
    "covered_replicates": 3,
    "replicate_count": 3,
    "mean_tokens": 1234.0,
    "max_tokens": 1500
  }]
}
```

`get_cost_summary`：

```json
{
  "replicate_count": 225,
  "metrics": {
    "input_tokens": {
      "covered_replicates": 225,
      "coverage_rate": 1.0,
      "mean": 1000.0,
      "p50": 900,
      "p95": 1800,
      "max": 3000
    },
    "output_tokens": {"...": "同上"},
    "total_tokens": {"...": "同上"},
    "student_total_tokens": {"...": "同上"},
    "hook_total_tokens": {"...": "同上；无 Hook 时统计值可为空"}
  }
}
```

`get_evaluation_case` 直接返回标准 `per_example.jsonl` 的一行：

> 这个返回的内容是不是有点啰嗦了，能否合并重复语义对视图进行压缩？这里连teacher judge的usage都列出来了，这完全没用；reasoning content也有占位的嫌疑，不过这个应该要从teacher judge下手，不返回原始reasoning_content，而是在返回评分值时的同时返回判断摘要

```json
{
  "example_id": "...",
  "question": "...",
  "golden_answer": "...",
  "predicted_answer": "...",
  "score": 0,
  "score_source": "static|teacher|null",
  "stability": "...",
  "requested_rollouts": 3,
  "completed_rollouts": 3,
  "scored_rollouts": 3,
  "correct_count": 0,
  "unresolved_count": 0,
  "success_rate": 0.0,
  "score_std": 0.0,
  "all_correct": false,
  "any_correct": false,
  "majority_correct": false,
  "answer_consistency": 1.0,
  "answer_distribution": {...},
  "run_status": "...",
  "run_status_counts": {...},
  "failed_replicate_ids": [],
  "unresolved_replicate_ids": [],
  "execution": {...},
  "replicates": [{
    "replicate_id": "r000",
    "replicate_index": 0,
    "sampling_seed": 42,
    "predicted_answer": "...",
    "run_status": "...",
    "runner_error": null,
    "score": 0,
    "score_source": "...",
    "static": {"decision": "...", "metrics": {...}, "reason": "..."},
    "teacher": {"score": 0, "raw_output": "...", "error": null, "metadata": {...}},
    "execution": {"steps": 2, "model_calls": 2, "tool_calls": 1, "retriever_errors": 0, "duplicate_queries": 0, "tokens": {...}}
  }]
}
```

`get_student_trajectory(view="behavior")`：

> 所有检索工具调用形式的轨迹都有这个问题：tool_result.payload.content已经返回过一遍了，但metadata.results中又呈现一遍，徒增消耗。还有最后的omitted字段，都属于决定要省略不看的部分了还提了一嘴，况且也没有这些信息的访问渠道，不如在视图中直接清除干净

```json
{
  "view": "behavior",
  "example": {
    "example_id": "...",
    "question": "...",
    "golden_answer": "...",
    "task_type": "...",
    "difficulty": "...",
    "filter_status": "..."
  },
  "replicate": {
    "replicate_id": "r000",
    "evaluation": {
      "score": 0,
      "score_source": "...",
      "predicted_answer": "...",
      "run_status": "...",
      "runner_error": null,
      "static_decision": "...",
      "static_metrics": {...},
      "teacher_score": 0,
      "teacher_error": null,
      "execution": {"steps": 2, "model_calls": 2, "tool_calls": 1, "retriever_errors": 0, "duplicate_queries": 0}
    }
  },
  "run": {"status": "completed", "answer": "...", "error": null},
  "events": [{"index": 1, "step": 1, "event_type": "model_output|parsed_output|tool_call|tool_result|hook_applied|...", "payload": {...}}],
  "omitted": ["repeated model_input messages", "provider usage metadata", "rollout provenance and filesystem paths", "unselected internal trace events"]
}
```

`view="full"` 返回完整 Rollout Record：

```json
{
  "example": {"example_id": "...", "question": "...", "answer": "...", "metadata": {...}, "source_path": "...", "line_number": 1},
  "replicate": {"replicate_id": "r000", "index": 0, "sampling_seed": 42},
  "harness": {...},
  "provenance": {...},
  "run": {"question": "...", "answer": "...", "status": "...", "error": null, "state": {...}, "trace": [{...}]}
}
```

`get_harness_manifest`：

> 只给harness_manifest拓扑视图但是不给具体实现的暴露接口，在多generation下难以归因已有manifest的问题。甚至analyst都没考虑从提示词上考虑问题

```json
{
  "schema_version": 1,
  "harness_id": "...",
  "tools": [{"instance_id": "...", "entrypoint": "...", "config": {...}}],
  "prompt": {"instance_id": "...", "entrypoint": "...", "config": {...}},
  "output": {"instance_id": "...", "entrypoint": "...", "config": {...}},
  "extensions": [{"instance_id": "...", "entrypoint": "...", "config": {...}}]
}
```

### 2.3 冗余与可读性

- `list_evaluation_cases` 是清楚的选择视图；`list_evaluation_cases_by_cost` 与它重复 `example_id/question/stability/success_rate`，但因排序目的不同，属于可接受的目录级重复。更简单的接口可以是一个 `list_evaluation_cases(order_by="example_id|mean_tokens", token_metric=...)`，当前拆分并未造成明显模型负担。
- `get_evaluation_case` 原样返回完整报告行，聚合字段、replicate 字段及 `teacher.raw_output/metadata` 同时出现。Failure Analyst 主要需要样本稳定性、每次答案/评分和执行摘要，通常不需要 Judge 原始输出及全部 token 细目。可增加默认 `summary` 视图，把原始行保留为 `full`。
- behavior trajectory 已主动删除重复 `model_input` 和文件路径，整体边界合理；其中 `replicate.evaluation.predicted_answer` 与 `run.answer` 通常重复，但一个属于判分事实、一个属于运行终态，保留两者仍可解释。
- `view="full"` 会重新引入完整 state、重复 model input、provider metadata 和路径，只适合诊断运行时故障，不应成为常规分析默认值；当前默认是 behavior，设计正确。
- `get_harness_manifest` 暴露 entrypoint 和 config 等装配细节，但没有提供行为摘要或组件源码。对 Failure Analyst 而言更简单的 `harness_topology` 视图会比原始 Manifest 更易读；当前返回没有严重重复，只是抽象层级偏实现。

## 3. Hypothesis Researcher

### 3.1 工具签名与用途

> 同样，harness_manifest的摘要和具体实现的无法访问，使得researcher不会提出修改prompt、output的简单解决方案，当然researcher的prompt和输出协议也要背锅。

| 工具签名 | 用途 |
| --- | --- |
| `get_student_trajectory(example_id: str, replicate_id: str, view: Literal["behavior", "full"] = "behavior")` | 读取 Failure Analyst 已引用轨迹的 behavior 视图；程序禁止该角色使用 full，并移除 golden answer。 |
| `get_intervention_capabilities()` | 返回可恢复 Hook phase、可见 stage、可用动作与执行限制。 |
| `list_trial_evidence()` | 在 Reviewer 回流修订时列出显式附加的 Trial 目录。 |
| `get_trial_evidence(trial_ref: str)` | 在 Reviewer 回流修订时读取一条 Trial 的 source/branch/worker 证据目录。 |
| `get_trial_event(trial_ref: str, stream: Literal["source", "branch", "worker"], event_index: int)` | 从 Trial 目录按索引展开一个精确事件。 |

`get_student_trajectory`、`list_trial_evidence`、`get_trial_evidence` 与 `get_trial_event` 的结构分别见第 2.2 节和第 5.2 节；Researcher 的 behavior trajectory 中没有 `example.golden_answer`，且 `omitted` 会增加 `"golden answer"`。

`get_intervention_capabilities`：

```json
{
  "schema_version": 2,
  "source_contracts": ["...内部源码契约标识..."],
  "execution": {
    "one_action_per_activation": true,
    "multiple_phases_per_trial": true,
    "same_worker_transcript_across_activations": true,
    "maximum_phase_directives": 4,
    "unique_phase_directives": true,
    "action_application": "current_hook_activation",
    "student_continues_from_selected_prefix": true,
    "teacher_loop_inside_actor": false,
    "context_patch_is_atomic": true
  },
  "observability": {
    "selected_prefix": ["selector.step", "selector.phase", "question", "editable_context.block_id", "..."],
    "full_block_content": "on_demand_by_numeric_block_id",
    "program_metadata": "hidden_and_preserved",
    "active_stage": "phase-specific values listed under each phase.stage",
    "native_reasoning": "trace_only_not_hook_visible",
    "inband_thinking": "..."
  },
  "phases": [{
    "phase": "post_tool",
    "stage": [{"key": "tool_result", "type": "...", "stability": "...", "note": "..."}],
    "native_reasoning_visible": false
  }],
  "actions": [{
    "name": "apply_context_patch|defer_final_answer|continue_without_change",
    "effect": "...",
    "compatible_phases": ["..."],
    "persistence": "next_generation|branch_prefix|none"
  }],
  "student": {"harness_id": "...", "tools": ["retriever_search", "..."]}
}
```

### 3.2 冗余与可读性

- Researcher 的 trajectory 权限和投影是当前最清楚的证据边界之一：只允许 Analyst 引用、强制 behavior 视图并移除 golden answer。
- `get_intervention_capabilities` 同时用 `phases[].stage`、`observability.active_stage` 和 `actions[].compatible_phases` 表达 phase/action 关系，模型需要在三个位置自行 join；`source_contracts` 是内部实现标识，对 Researcher 决策帮助很小。更简单的视图应按 phase 直接列 `observable_inputs`、`available_actions`、`limits`，把全局执行不变量单列。
- `teacher_loop_inside_actor` 使用已废弃的 Actor 词，且九个布尔/字符串执行字段混合表达约束；可以改为少量强语义规则数组，降低漏读风险。
- Trial 工具仅在 continuation 有附加 Trial 时有价值；初始 Researcher 调用看到这些工具但通常没有 Trial，这增加了工具选择噪声。若 Runner 支持按 continuation 动态工具集，可以只在回流时暴露。

## 4. Intervention Executor

Intervention Executor 的 Manifest 没有静态工具；每次 Hook activation 由程序动态暴露查询和动作工具。这里只列三个查询工具。

### 4.1 工具签名与用途

| 工具签名 | 用途 |
| --- | --- |
| `inspect_active_observation()` | 读取当前 phase、Student step、活动 stage 和既往干预次数。 |
| `inspect_editable_context()` | 以数字 block ID、角色、字符数和短摘要列出 Student 可见上下文。 |
| `inspect_context_block(block_id: int)` | 按数字 ID 展开一个块的完整 Student-visible 内容。 |

### 4.2 返回结构

`inspect_active_observation`：

```json
{
  "phase": "post_tool|pre_final|...",
  "student_step": 2,
  "active_stage": {
    "tool_result": {"active": true},
    "final_decision": {"action": "accept", "answer": "..."}
  },
  "lifecycle_facts": {
    "active_stage_keys": ["tool_result"],
    "prior_intervention_count": 1
  }
}
```

除 `final_decision` 外，stage 值只显示 `{"active": true}`；完整 Student 可见内容由 block 工具读取。

`inspect_editable_context`：

```json
[
  {
    "block_id": 1,
    "kind": "message|tool_result",
    "role": "system|user|assistant|tool",
    "characters": 123,
    "summary": "最多约 120 字符的单行摘要…"
  }
]
```

`inspect_context_block`：

```json
{
  "block_id": 1,
  "kind": "message|tool_result",
  "role": "system|user|assistant|tool",
  "content": "完整 Student-visible 内容"
}
```

未知 ID 不返回 JSON，而返回纯文本 `TOOL_INPUT_ERROR: unknown block_id N`，同时在 ToolResult metadata 中保存错误。

### 4.3 冗余与可读性

- activation user message 已完整嵌入与 `inspect_active_observation()` 相同的 JSON，因此该工具目前是精确重复；它只提供“重新读取”价值。应二选一：保留消息内 observation 并删除工具，或只在消息中说明 activation identity、由工具按需读取 observation。前者改动更小。
- `active_stage` 和 `lifecycle_facts.active_stage_keys` 重复表达活动 key；保留前者即可从对象键推导后者。
- `inspect_editable_context → inspect_context_block` 是合理的渐进展开。单块返回再次携带 `block_id/kind/role` 属于必要校验上下文，重复很小。
- 摘要同时返回 `characters` 与 `summary` 有助于判断是否值得展开，不建议删除。
- 错误返回有时是 JSON、有时是纯文本，增加调用方分支；可以统一为 `{"status":"error","reason":"unknown_block_id","block_id":N}`。

## 5. Trial Reviewer

### 5.1 工具签名与用途

| 工具签名 | 用途 |
| --- | --- |
| `get_trial_evidence(trial_ref: str)` | 读取当前被分配 Trial 的完整判断目录；提交前程序强制调用。 |
| `get_trial_event(trial_ref: str, stream: Literal["source", "branch", "worker"], event_index: int)` | 按目录索引读取一个未经摘要替代的精确事件。 |

Trial Reviewer 没有注册 `list_trial_evidence`，因为输入已绑定唯一 Trial reference。

### 5.2 返回结构

`list_trial_evidence`（由 Researcher 和 Distiller 使用）先给出目录：

```json
{
  "trial_count": 3,
  "items": [{
    "trial_ref": "execute_trial-...",
    "intent": "...",
    "worker_result": {"result_kind": "executed|unsuitable_assignment", "activated_phases": [...], "modified_phases": [...], "unmet_phases": [...]},
    "source": {"example_id": "...", "replicate_id": "r000", "fork_step": 1, "fork_phase": "post_tool", "...": "去除 rollout_file/source_run 后的 selector"},
    "phase_plan": [...],
    "activation_counts": {...},
    "phase_effects": [...],
    "comparison": {...}
  }]
}
```

`get_trial_evidence`：

```json
{
  "trial_ref": "execute_trial-...",
  "intent": "...",
  "worker_result": {...},
  "source": {
    "selector": {...},
    "run": {
      "question": "...",
      "answer": "...",
      "status": "...",
      "error": null,
      "state": {"...": "已去除 model_inputs/model_outputs/parsed_outputs/tool_interactions/conversation_messages"},
      "events": [{"event_ref": "source/0", "event_index": 0, "event_type": "...", "step": 1, "detail": {...}}]
    }
  },
  "action": {...},
  "phase_plan": [...],
  "activation_budgets": {...},
  "activation_counts": {...},
  "context_changes": [...],
  "phase_effects": [...],
  "worker_events": [{"event_ref": "worker/0", "event_index": 0, "event_type": "...", "detail": {...}}],
  "branch_run": {"question": "...", "answer": "...", "status": "...", "error": null, "state": {...}, "events": [{...}]},
  "run_scopes": {"source": "...", "branch": "...", "worker": "..."},
  "comparison": {...}
}
```

事件目录的 `detail` 随类型变化：model input 只给消息数/角色/字符数，model output 给字符数/preview/reasoning 是否存在/工具名，tool call 给 name/arguments，tool result 给字符数/preview，parsed output 给解析结果与 thinking 长度/preview。

`get_trial_event`：

```json
{
  "trial_ref": "execute_trial-...",
  "stream": "source|branch|worker",
  "event_index": 12,
  "event": {"event_type": "...", "step": 2, "payload": {...}, "metadata": {...}}
}
```

精确事件会删除 usage；Worker ToolResult 还会删除程序 metadata，但保留实际内容和动作参数。

### 5.3 冗余与可读性

- `list_trial_evidence` 已包含 `worker_result/source/phase_plan/activation_counts/phase_effects/comparison`，随后 `get_trial_evidence` 几乎全部重复。目录最好只保留 `trial_ref`、案例身份、intent、phase 和极短 outcome，详细事实只在 get 中出现。
- `get_trial_evidence` 同时返回派生的 `phase_effects/comparison/context_changes` 和三条事件目录。这里的重复有审计价值：前者用于快速判断，后者用于追溯；但当前没有明确区分 `summary` 与 `catalog`，字段较多且平铺，模型容易把派生结论误当原始事件。建议改成 `summary`、`streams`、`event_access` 三层。
- Trial Reviewer 提交前被强制调用一次 `get_trial_evidence`，因此该响应的固定开销会落到每条 Trial 上。更合适的角色视图是 `trial_judgment_view`：按冻结 phase 只给 predicate 是否满足、动作是否正确执行、即时 Student response、source/branch outcome 与相关 event refs；有判定缺口时再用 `get_trial_event` 展开。
- 每个目录事件同时返回 `event_ref="source/12"` 和 `event_index=12`，而且所在容器已经说明 stream，信息重复。保留 `event_index` 即可。
- `run_scopes` 是每次调用都相同的文档文本，应该放入工具描述，不应随 Trial 重复返回。
- 按 `get_trial_event` 展开精确事件的设计合理，避免默认传入完整 source/branch/worker transcript。

## 6. Evidence Reviewer

Evidence Reviewer 当前没有查询工具。完整 Trial Review、程序维护的 coverage summary 和剩余预算由 Controller 直接放入 Role Input/continuation。这避免角色再次读取 Trial 原始轨迹，也意味着其判断质量完全依赖上游 Trial Reviewer 投影是否充分。

## 7. Mechanism Distiller

### 7.1 工具签名与用途

| 工具签名 | 用途 |
| --- | --- |
| `list_trial_evidence()` | 列出附加 Trial 及其快速事实。 |
| `get_trial_evidence(trial_ref: str)` | 读取一条 Trial 的 source/branch/worker 判断目录。 |
| `get_trial_event(trial_ref: str, stream: Literal["source", "branch", "worker"], event_index: int)` | 按需读取精确 Trial 事件。 |
| `probe_mechanism_evaluators(draft_id: str, evidence_refs: list[str], repetitions: int = 3)` | 使用正式 Hook-model backend 重复运行草稿中的 `hook_model` predicate fixtures，并返回分类一致性诊断。 |

前三项结构和问题见第 5.2–5.3 节。

`probe_mechanism_evaluators` 的模型可见返回会去掉逐次 observation：

```json
{
  "draft_id": "mechanism_draft_001",
  "probed_phase_count": 1,
  "summaries": [{
    "schema_version": 1,
    "predicate_ref": "phase-1:pre_final",
    "profile": "student",
    "repetitions": 3,
    "fixture_summaries": [{
      "fixture_id": "...",
      "expected_label": "positive|negative|uncertain",
      "observed_label_counts": {"positive": 3},
      "match_rate": 1.0,
      "consistent": true,
      "parse_failure_count": 0
    }],
    "label_match_rate": 1.0,
    "consistent_fixture_count": 3,
    "parse_failure_count": 0,
    "usage": {"input_tokens": 1000, "output_tokens": 30, "total_tokens": 1030}
  }]
}
```

完整 artifact 另行保存每次 observation：`fixture_id/repetition/expected_label/observed_label/raw_output/parse_error/usage`。

### 7.2 冗余与可读性

- Trial 查询继承第 5.3 节的问题；Distiller 已在 Role Input 中收到结构化 Trial Review 和 coverage summary，再开放完整 Trial 目录形成第二套证据表达。它适合核验边界，但不应要求无差别读取全部 Trial。
- Probe 返回的 `fixture_summaries` 和全局 `label_match_rate/consistent_fixture_count/parse_failure_count` 是合理的明细与汇总两层，不属于有害重复。
- `schema_version/profile/repetitions` 在同一次 draft 的每个 phase summary 中重复，体积影响很小；可以上提到顶层，但优先级低。
- 逐次 raw output 已从工具回显中移除、只存 artifact，这是良好的上下文控制。
- `consistent` 只表示重复调用标签一致，不表示标签符合 `expected_label`，字段名容易被误读为“稳定且正确”；`fixture_id` 又没有附带 case-neutral observation 摘要，Distiller 难以定位具体是哪类边界不稳定。
- parse failure 只回传次数，不回传错误类别。更有操作性的紧凑结果应保留 fixture 的抽象 observation、expected/observed counts 和 parse-error category，减少可从明细推导的聚合数字。

## 8. Mechanism Compiler

Compiler 的 capability packet 是 Role Input 自动注入内容，不是查询工具返回；本文不把 packet 伪列为工具。当前 Manifest 也没有暴露代码中仍存在的 `get_hook_authoring_guide` 或 `list_hook_api_symbols` 工厂。

### 8.1 工具签名与用途

| 工具签名 | 用途 |
| --- | --- |
| `list_harness_files()` | 列出当前内存 Candidate Workspace 中所有文件和字节数。 |
| `read_harness_file(path: str)` | 读取 Candidate Workspace 中一个 UTF-8 文件的完整内容。 |
| `query_hook_api(symbol: str)` | 按 Runtime Input Topic、精确公开 symbol 或搜索短语查询 Hook API 契约，并报告查询预算。 |

### 8.2 返回结构

`list_harness_files`：

```json
{
  "revision": 2,
  "items": [{"path": "extensions/example/component.py", "bytes": 1234}]
}
```

`read_harness_file`：

```json
{"path": "harness.json", "content": "完整 UTF-8 文件内容"}
```

`query_hook_api("tool")`（Topic）：

```json
{
  "status": "resolved",
  "query_kind": "runtime_input_topic",
  "query": "tool",
  "document": {
    "runtime_input_id": "tool",
    "description": "...",
    "preferred_usage": ["..."],
    "avoid": ["..."],
    "lifecycle_notes": ["..."],
    "symbols": ["stage.tool_call", "stage.tool_result", "core.tool_interactions", "..."],
    "native_reference": "Python-native 类型和签名文本"
  },
  "source": "capability_packet|runtime_input_registry",
  "remaining_unique_queries": 12
}
```

`query_hook_api("HookContext.call_model")`（精确 symbol）：

```json
{
  "status": "resolved",
  "query_kind": "symbol",
  "query": "HookContext.call_model",
  "contract": {
    "kind": "method|class|state_key|runtime_view",
    "symbol": "HookContext.call_model",
    "signature": "...",
    "type": "...",
    "summary": "...",
    "note": "...",
    "parameters": [...],
    "returns": {...},
    "stability": "stable|experimental",
    "shape": "closed|open",
    "...": "随 contract kind 变化"
  },
  "native_reference": "由同一 contract 渲染的 Python-native 文本",
  "related_runtime_inputs": ["model_io"],
  "source": "capability_packet|continuation_query|exact_query",
  "remaining_unique_queries": 11
}
```

未知查询：

```json
{
  "status": "rejected",
  "reason": "unknown_query|empty_query|query_budget_exhausted",
  "query": "...",
  "runtime_input_suggestions": ["..."],
  "symbol_suggestions": ["..."],
  "remaining_unique_queries": 11
}
```

### 8.3 冗余与可读性

- `list_harness_files` 和 `read_harness_file` 都很简单；`revision` 对一次列表结果有审计价值，文件字节数能帮助模型控制读取范围。
- `read_harness_file` 总是返回完整内容，没有行范围或片段读取。当前模板文件普遍不大，尚可接受；对于长源文件，更简单的维护方式不是裁剪语义，而是增加可选 `start_line/end_line`。
- 精确 symbol 查询同时返回结构化 `contract` 和从该 contract 渲染的 `native_reference`，语义显著重复。对 LLM 来说 Python-native 文本通常更直接；对程序审计则结构化 contract 更稳定。建议工具默认返回 native reference + 最小 metadata，并用 `view="structured"` 按需取得 contract，或反向设计为 `view="native|structured|both"`，默认不要 `both`。
- Topic 返回 `symbols` 后又在 `native_reference` 中逐个展开这些 symbol，属于目录与正文的轻度重复，但有导航价值；可保留 symbols，只要不再同时返回完整结构化 contracts。
- `source` 与 `remaining_unique_queries` 清楚地说明预算和来源，不应删除。

## 9. Conformance Reviewer

Conformance Reviewer 当前没有查询工具。Controller 直接提供 `candidate_trajectory_view`、Mechanism Spec、reference observations 和 Trial refs。该角色已经使用专用裁剪视图，不会通过工具读取完整 Candidate rollout；这与 Candidate Reviewer 当前做法形成明显差异。

## 10. Candidate Reviewer

### 10.1 工具签名与用途

| 工具签名 | 用途 |
| --- | --- |
| `list_candidate_changes(page: int = 1, page_size: int = 10, change: Literal["any", "improved", "regressed", "unchanged"] = "any")` | 分页列出每个 Example 的 incumbent/candidate success-rate 变化。 |
| `get_candidate_case(example_id: str)` | 返回一个 Example 的配对 Evaluation 详情及各 replicate 结果。 |
| `get_paired_student_trajectory(example_id: str, replicate_id: str)` | 并排返回同一 Example/replicate 的 incumbent 与 candidate Student rollout 投影。 |
| `get_candidate_harness_diff()` | 返回 Candidate Template 相对 Incumbent Template 的完整文件 diff。 |

### 10.2 返回结构

`list_candidate_changes`：

```json
{
  "page": 1,
  "page_size": 10,
  "total_items": 75,
  "total_pages": 8,
  "items": [{
    "example_id": "...",
    "question": "...",
    "change": "improved|regressed|unchanged",
    "incumbent_success_rate": 0.0,
    "candidate_success_rate": 0.67,
    "success_rate_delta": 0.67,
    "incumbent_status": "...",
    "candidate_status": "..."
  }]
}
```

`get_candidate_case`：

```json
{
  "example_id": "...",
  "question": "...",
  "incumbent": {
    "success_rate": 0.0,
    "stability": "stable_failure",
    "run_status": "...",
    "execution": {...},
    "replicates": [{"replicate_id": "r000", "score": 0, "run_status": "...", "predicted_answer": "...", "runner_error": null, "execution": {...}}]
  },
  "candidate": {
    "success_rate": 0.67,
    "stability": "unstable",
    "run_status": "...",
    "execution": {...},
    "replicates": [{"replicate_id": "r000", "score": 1, "run_status": "...", "predicted_answer": "...", "runner_error": null, "execution": {...}}]
  }
}
```

`get_paired_student_trajectory` 当前实际结构：

```json
{
  "example_id": "...",
  "replicate_id": "r001",
  "incumbent": {
    "harness": {"source_type": "...", "version_store": "...", "version_store_id": "...", "version_id": "...", "candidate_digest": null},
    "provenance": {"schema_version": 1, "dataset": {...}, "model": {...}, "harness": {...}, "execution": {...}},
    "run": {"question": "...", "answer": "...", "status": "...", "error": null, "trace": [{"index": 0, "step": 1, "event_type": "model_input|model_output|...", "payload": {...}]}
  },
  "candidate": {
    "harness": {...},
    "provenance": {...},
    "run": {"question": "...", "answer": "...", "status": "...", "error": null, "trace": [{...}]}
  }
}
```

该投影只删除 Rollout 顶层的 `example`、`replicate` 以及 `run.state`，但完整保留两边的原始 `run.trace`；其中包括每一步重复增长的 `model_input`、完整 model output metadata、Hook-model output 和 provider usage。

`get_candidate_harness_diff`：

```json
{
  "available": true,
  "incumbent_digest": "...",
  "candidate_digest": "...",
  "changes": [{"path": "extensions/example/component.py", "operation": "add|modify|delete", "diff": "完整 unified diff"}]
}
```

未配置模板根时返回：

```json
{"available": false, "reason": "candidate Harness roots were not configured", "changes": []}
```

### 10.3 `get_paired_student_trajectory` 实测

在 `20260806_qwen3-8b` 的 Candidate Reviewer artifact 中，该工具被调用两次，返回 JSON 文本分别为 154,367 和 163,996 字符。第二条返回中：

| 部分 | incumbent | candidate |
| --- | ---: | ---: |
| trace event 数 | 10 | 53 |
| `model_input` 序列化字符 | 5,749 | 53,503 |
| `hook_model_output` 序列化字符 | 0 | 39,663 |
| `hook_applied` 序列化字符 | 0 | 18,507 |
| `model_output` 序列化字符 | 2,871 | 16,597 |
| `tool_result` 序列化字符 | 7,133 | 10,862 |

两次调用仅工具返回就约 318k 字符。Candidate 侧每次 `model_input` 都包含此前上下文，因此同一问题、system prompt、历史检索结果和反馈会被重复多次；`harness`、`provenance` 和 `run.question` 还在 incumbent/candidate 两侧各出现一次。

现有 Conformance trajectory projection 已证明同类裁剪可行：对本实验一条 211,678 字符的原始 Candidate record，专用投影为 18,912 字符，约为原记录的 8.9%，同时仍保留 Hook model 输出、Hook 修改、工具交互、最终决策和错误。Candidate 视图不能原样照搬 Conformance 判断字段，但可以复用其事件过滤与 context-change delta 投影。

### 10.4 冗余与可读性

- `list_candidate_changes` 是合理的目录视图，但 Candidate Reviewer 为覆盖所有 75 题曾连续读取四页，问题文本和状态字段占据较多上下文。Reviewer 通常只需要先看 improved/regressed，再按需抽取 unchanged；提示词和默认调用可以优先使用 change filter。
- `get_candidate_case` 没有把目录中的 `change` 和 `success_rate_delta` 带回，要求模型记住上一工具结果；同时两侧都返回 aggregate `execution` 和每 replicate `execution`。建议在顶层增加 `comparison`，保留 per-side summary，再按需展开 replicate。
- `get_paired_student_trajectory` 是当前查询工具中冗余最严重、结构最不利于角色判断的一项：它没有复用已有 `_behavior_trajectory` 或 Conformance view；重复 model input 体积大；两条 trace 长度不同且没有对齐；没有携带 score、steps、tool calls、tokens 或 delta；模型必须在海量原始事件中同时重建运行结果和差异。
- `harness` 和 `provenance` 对“单题行为为何改善/回归”通常不是逐次必要输入。版本身份可以在顶层各保留一个短 ID；模型配置、数据集路径和执行配置应由 Role Input 提供一次，而不是每条 trajectory 重复。
- `get_candidate_harness_diff` 的完整 unified diff 对实现核查必要，但 digest 对模型判断帮助有限；多文件或大文件时应支持目录摘要后按 path 展开。当前候选通常只改少量文件，优先级低于 trajectory 修复。

### 10.5 建议的配对行为视图

不改变 Candidate Reviewer 的判断职责，最小可用改法是让 `get_paired_student_trajectory` 增加 `view: Literal["behavior", "full"] = "behavior"`，默认返回：

```json
{
  "example_id": "...",
  "replicate_id": "r001",
  "question": "只出现一次",
  "comparison": {
    "change": "improved|regressed|unchanged",
    "incumbent": {"score": 0, "answer": "...", "status": "completed", "steps": 2, "model_calls": 2, "tool_calls": 1, "total_tokens": 1700},
    "candidate": {"score": 1, "answer": "...", "status": "completed", "steps": 5, "model_calls": 5, "tool_calls": 3, "total_tokens": 12000},
    "delta": {"score": 1, "steps": 3, "model_calls": 3, "tool_calls": 2, "total_tokens": 10300}
  },
  "incumbent_events": [{"step": 1, "event_type": "model_output|parsed_output|tool_call|tool_result|final_answer", "payload": {...}}],
  "candidate_events": [{"step": 1, "event_type": "model_output|parsed_output|tool_call|tool_result|hook_model_output|hook_applied|final_deferred|final_answer", "payload": {...}}],
  "omitted": ["repeated model_input", "provider usage metadata", "filesystem provenance", "duplicate static configuration"]
}
```

该视图应复用 behavior projection 的事件筛选，并补保留 Candidate 判断所需的 Hook model label/input 摘要、Hook change、defer feedback 和状态预算；不要直接复用完整 Conformance 输入，因为 Candidate Reviewer 关心的是效果与成本，不需要逐 predicate 的全部 reference observation。`full` 只作为运行时故障诊断的显式选项。

## 11. 跨角色结论与优先级

| 优先级 | 问题 | 影响 |
| --- | --- | --- |
| 高 | Candidate Reviewer 的 paired trajectory 返回两份原始 trace | 单次可达 150k–164k 字符，重复上下文显著，模型需要自行对齐且缺少配对指标。 |
| 中 | Intervention active observation 在消息和工具中完全重复 | 每个 activation 重复同一生命周期 JSON，工具本身没有新增信息。 |
| 高 | Trial list/get 重复大部分派生字段，get 内 summary/catalog 平铺 | 每条 Trial Review 都强制读取，持续增加上下文，并模糊派生结论与原始事件目录的层级。 |
| 中 | Compiler exact API query 同时返回 contract 与 native reference | 同一契约双重表达；可按 view 选择，默认只给模型更易用的一种。 |
| 低 | Evaluation case 返回完整报告行 | Judge 原始输出、metadata 与细粒度 token 对 Failure Analyst 通常过多。 |
| 低 | Harness Manifest 和 Harness diff 偏实现视角 | 当前体积通常可控，但可增加目录/拓扑摘要与按 path 展开。 |

当前最值得先改的是 Candidate Reviewer 的配对行为视图。项目已经有 `_behavior_trajectory` 和 Conformance trajectory view 两个可参考实现，无需设计新的通用轨迹抽象；应先在 CandidateComparisonStore 内建立职责专用的最小投影，再用现有 `20260806_qwen3-8b` 两条已检查案例比较返回体积与 Reviewer 信息完备性。

## 12. 主要代码依据

- 工具注册与签名：`search_harness/evolution/research/tools.py`
- Evaluation/Trial 资源投影：`search_harness/evolution/research/resources/base.py`
- Compiler/Candidate Comparison 投影：`search_harness/evolution/research/resources/stores.py`
- Intervention 动态查询工具：`search_harness/evolution/research/intervention/worker.py`
- Editable Context Block 投影：`search_harness/evolution/research/intervention/bridge.py`
- Intervention 能力目录：`search_harness/evolution/research/intervention/capabilities.py`
- Hook API 查询：`search_harness/evolution/research/mechanism/hook_api.py`
- 当前角色实际工具闭集：`harness_templates/teacher/<role_id>/harness.json`
