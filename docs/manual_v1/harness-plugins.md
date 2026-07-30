# Harness Plugins

## 文档职责

本文档规定外部 Harness plugin root 的当前装配协议。它描述已实现的 manifest、factory 和 Hook 接口。Git-backed Harness 版本管理与线性演化工作流已经实现，相关持久化和恢复边界见 [Harness Checkpoint Store](version-store.md) 与 [Evolution Runner](evolution_runner.md)。

## 核心边界

`search_harness/core/` 不包含具体工具、prompt 或 hook。它只接收已组装的 `PromptBuilder`、`ToolRuntime` 与 `HookPipeline`。

一个 `plugins_root` 是一套完整 Harness 实例，运行入口通过 `--plugins-root` 选择它。仓库提供的基线实例位于：

```text
harness_templates/actor/baseline/plugins/
```

其结构为：

```text
<plugins_root>/
  harness.json
  tools/<plugin_name>/plugin.py
  prompts/<plugin_name>/plugin.py
  prompts/<plugin_name>/templates/
  extensions/<plugin_name>/plugin.py
  extensions/<plugin_name>/helper.py
```

`registry` 只读取 `harness.json` 中显式声明的 entrypoint，不自动扫描目录。

## Manifest

`harness.json` 必须为 UTF-8 JSON，并包含：

```json
{
  "schema_version": 1,
  "harness_id": "baseline_search",
  "tools": [{"instance_id": "search", "entrypoint": "tools/retriever_search/plugin.py:build", "config": {}, "evolution_policy": "fixed"}],
  "prompt": {"instance_id": "simple_search", "entrypoint": "prompts/simple_search/plugin.py:build", "config": {}, "evolution_policy": "fixed"},
  "extensions": []
}
```

所有 `instance_id` 必须唯一。entrypoint 使用相对 plugins root 的 `relative_file.py:factory_name` 形式，不能使用绝对路径或 `..` 路径。

`evolution_policy` 可取：

- `fixed`：表达该组件的 manifest 条目、配置和所属组件目录将由未来演化流程保护；
- `mutable`：表达该组件允许被未来演化 patch 修改。

Version Store 会以父版本 manifest 执行该策略。模型通过受控接口新增的组件总是 `mutable`，不允许模型创建新的 `fixed` 组件。完整规则见 [Harness Version Store](version-store.md)。

## Factory 协议

registry 创建 `PluginContext(plugins_root, env_file)` 并按组件类别调用 factory：

```python
# tools
def build(config: dict[str, Any], context: PluginContext) -> DefinedTool: ...

# prompt
def build(
    config: dict[str, Any],
    context: PluginContext,
    tools: ToolSet,
) -> PromptBuilder: ...

# extensions
def build(
    config: dict[str, Any],
    context: PluginContext,
) -> BaseHook | Iterable[BaseHook]: ...
```

工具 factory 的返回对象必须同时具有 `name`、`definition` 和 `run(arguments)`；PromptBuilder 必须具有 `build(state)`；extension factory 必须返回 `BaseHook` 实例或其实例序列。Factory 参数中的 `config` 是对应 manifest 条目的副本，插件不得依赖隐式全局注册状态。

每个组件目录会作为独立的 synthetic Python package 加载，因此 `plugin.py` 可以使用 `from .helper import ...` 等相对导入组织多文件实现。一个组件目录只对应一个 manifest 组件；当前设计不以同一个 hook 实现被多个组件复用为目标。

## Hook 协议

`BaseHook` 是 core 中的抽象基类。具体 hook 必须声明：

- `hook_id`：一次 Harness 装配内唯一的实例 ID；
- `phases`：订阅的 Hook phase 集合；
- `state_refs`：可持久写入的 extension/shared 状态；
- `writable_stage_keys`：允许改写的当前阶段主载荷；
- `model_profiles`：允许该 hook 使用的小模型 profile；默认空集表示禁止调用模型；
- `max_model_calls_per_invocation`：单次 hook 触发允许的最大模型调用数，默认 `1`；
- `handle(context)`：唯一的触发入口。

`HookPipeline` 依照 manifest 中 extension 的顺序执行订阅当前 phase 的 hook，并统一提交事务、记录 `hook_applied` 和 `hook_error`。具体 hook 不应自行处理 trace 或越过 `HookContext.state` 修改状态。

### Hook 内的小模型调用

Hook 通过 `context.call_model(HookModelRequest(...))` 使用框架提供的模型能力，不应自行创建 HTTP 客户端或嵌套运行另一个 `AgentLoop`。当前 registry 只为声明了 `model_profiles = frozenset({"student"})` 的 hook 按需装配 `STUDENT_*` 模型；未声明 profile、超出单次调用上限或后端不可用都会失败并留下 `hook_model_error`。

```python
request = HookModelRequest(
    profile="student",
    purpose="classify whether the latest result answers the question",
    model_input=ModelInput(messages=(
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=evidence),
    )),
)
response = context.call_model(request)
decision = response.json_object()
context.state.set("extension.result_filter.decision", decision)
```

教师生成的 hook 可以读取当期允许可见的 `core.*`、`stage.*`、`extension.*` 与 `shared.*`，并自行选择其中哪些内容进入 `HookModelRequest.model_input`。这意味着教师能够控制小模型上下文，但模型调用本身不隐式修改主流程：完整请求与原始回复先记录为独立 `hook_model_output`，只有 hook 随后通过 `context.state.set(...)` 提交的值才会出现在 `hook_applied.changes` 并影响 loop。模型回复的解析、异常处理与确定性 fallback 也属于 hook 实现职责。

实验模板中的 `result_summary_prompt` 同时订阅 `post_tool` 和 `post_prompt`：前者将 `extension.result_summary_prompt.pending` 置为 `true`，后者在下一轮 `stage.model_input` 末尾追加该实例定义的 `user` 策略消息，并立即将该标记复位为 `false`。它不改写工具调用或工具结果；每个成功工具调用恰好注入一次提示。

Student baseline 不包含格式诊断 hook。Core 只提供通用的 invalid-output 重试；是否为 Student 增加更具体的格式反馈属于可演化 Harness 能力。

Critic baseline 的 fixed `format_error_feedback` 订阅 `post_parse`，用于保障 Adapter 自身输出协议的可靠性。它读取 parser 实际消费的 `stage.parser_input` 和 `stage.parsed_output`，识别缺失的 `<tool_call>` / `<final_answer>` 开始或结束标签以及误用的 `<tool_use>`，并且只改写 `stage.parsed_output`。修改前后值由普通 `hook_applied` 事件完整记录。

### Hook 时机与阶段状态

每个 hook 都能读取完整的 `core.*` 投影、已声明的 `extension.*` / `shared.*` 状态和当前阶段存在的 `stage.*`。`stage.*` 只在本次 phase 内有效；只有在 `writable_stage_keys` 中声明的键才可改写。下表的“可改写主载荷”表示 hook 显式声明权限后的可改写值。

| Phase | 执行位置 | 可用 stage 状态 | 可改写主载荷 | 适用场景与关键时点 |
| --- | --- | --- | --- | --- |
| `pre_prompt` | 本轮 `PromptBuilder.build` 前 | 无 | 无 | 根据完整历史更新 extension 状态，或准备稍后注入 prompt 的标记；此时本轮 `ModelInput` 尚不存在。 |
| `post_prompt` | `PromptBuilder.build` 后、模型调用前 | `stage.model_input: ModelInput` | `stage.model_input` | 对本轮结构化消息作最后变换，例如追加 user message、删减上下文或改写 system prompt。修改后的值会被记录并传给模型。 |
| `post_model` | 模型文本生成后、parser 前 | `stage.raw_model_output: str` | `stage.raw_model_output` | 格式修复、输出清洗或模型特定的协议兼容。parser 消费改写后的字符串。 |
| `post_parse` | parser 得到 `ParsedOutput` 后、分支判断前 | `stage.parser_input: str`、`stage.parsed_output: ParsedOutput` | `stage.parsed_output` | 读取 parser 实际消费的文本，改写已解析动作或细化 invalid 原因；结果必须仍是 `ParsedOutput`。 |
| `pre_tool` | 工具执行前 | `stage.tool_call: ToolCall` | `stage.tool_call` | 审核、限制或规范化本次工具调用；trace 与 `ToolRuntime` 使用改写后的调用。 |
| `post_tool` | 工具返回后、写入 `state.tool_interactions` 前 | `stage.tool_call: ToolCall`、`stage.tool_result: ToolResult` | `stage.tool_call`、`stage.tool_result` | 通常用于观察或改写工具结果，并记录“刚发生工具调用”的准确因果点。此刻核心历史中尚未追加该 interaction；改写 `tool_call` 不会改变已经执行的调用，通常不应这样做。 |
| `pre_final` | 已识别最终答案后、结束 run 前 | `stage.final_decision: FinalDecision` | `stage.final_decision` | 控制本次终答。默认是 `FinalDecision.accept(candidate)`；Hook 可改写为 accept 的答案，或以 `FinalDecision.defer(feedback)` 暂缓结束。defer 会追加 assistant 原输出与 user feedback 后进入下一轮，并消耗当前步数。一个阶段中 defer 不可被后续 Hook 改回 accept。 |
| `on_error` | 工具错误或最大步数等原因导致终止后 | `stage.error: Exception` | 通常不改写 | 用于观察、持久记录或收集终止错误。此时 core 已进入终止状态，改写 stage error 不会改变 run 的终止结果。 |

工具成功分支的顺序是：`pre_tool` -> 工具执行 -> `post_tool` -> `state.append_tool_interaction(...)` -> 追加 assistant 原文与 user observation -> 下一轮 `pre_prompt` -> `PromptBuilder.build(...)` -> `post_prompt`。无效输出分支则是：parser -> `post_parse` 细化 invalid 原因 -> core 追加 assistant 原文与 user feedback -> 下一轮 `pre_prompt`。最终答案分支则是：parser -> `pre_final` 的 `FinalDecision` -> accept 后结束，或 defer 后追加 assistant 原文与 user feedback 并进入下一轮。因此，`post_tool` 看见的是当前工具的原始返回与调用，而下一轮 `post_prompt` 看见的是已包含该 interaction、纠错反馈或终答 defer 反馈的 `ModelInput`。

### 为什么跨阶段要写 extension 状态

以“工具结果后追加一条 user 提示”为例，`post_tool` 是确认工具刚刚成功完成的精确位置，但此时下一轮 `ModelInput` 还不存在；实际追加消息只能在下一轮的 `post_prompt` 改写 `stage.model_input` 完成。

`stage.*` 只在对应 Hook phase 的一次调用期间存在，phase 结束后立即清空。跨 phase
联动必须通过声明过的 `extension.*` 或 `shared.*` 状态传递；原始问题可在任意时机通过
`core.question` 读取。Version Store 校验会以无网络的 phase contract smoke 逐一触发已
注册 Hook，并拒绝读取或写入非当前 phase `stage.*` 键的候选。

这并不意味着 `post_prompt` 完全无法推断前面有工具调用：它可以检查 `core.tool_interactions` 等历史。不过该历史没有提供“本次 prompt 正是由哪一次 `post_tool` 触发”的显式标记，且 hook 还需自行避免对同一 interaction 重复注入。更清晰的做法是由 `post_tool` 写入一个很小的、一次性消费的 extension 状态，例如 `extension.result_summary_prompt.pending` 或 `pending_tool_step`；`post_prompt` 读取并消费它、追加消息后清除该状态。

这种状态不是为了弥补并发问题，而是将“工具结果已出现，需要对下一轮 prompt 施加一次策略”这一因果意图跨 phase 显式传递。它还会在 trace 中留下可审计的 before/after 记录。对当前单线程 loop 而言，布尔标记已足够；记录 tool step 则能让调试和去重语义更直观。

## 通用机制与具体实例

通用工具 schema 位于 `framework/tooling/`，通用 prompt renderer 位于 `framework/prompting/`。它们可以被任意外部 plugin 引用，但不包含任务特定的工具、模板或策略。

Student baseline 中只包含 Retriever 与 simple search prompt，不预装 extension。研究插件保留在 `harness_templates/experiments/`。Critic 的 format error feedback 位于 Critic plugin root。未来新增或演化出的工具、prompt、extension 应写入对应 plugins root，而不是写回 `search_harness/` 框架包。
