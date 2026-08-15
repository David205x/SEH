# Lifecycle 与 Component API

## Component Factory

Manifest entrypoint 指向可调用 Factory。共享 Assembly 以声明的 `config` 和 `ComponentFactoryContext` 调用它；Prompt 还可接收已装配的 ToolSet。Factory 应返回对应协议对象，不得在导入时执行运行任务。

`ComponentFactoryContext` 字段：

- `template_root: Path`
- `env_file: Path | None`
- `runtime_context: object | None`

Tool Factory 返回 `DefinedTool`；Prompt Factory 返回实现 `build(AgentState) -> ModelInput` 的对象；Output Factory 返回实现 `parse(str) -> ParsedOutput` 的对象；Extension Factory 返回单个对象或有序对象序列。Student 的 Extension 当前必须解析为 `BaseHook`。

`TaggedOutputParser` 对 `<tool_call>` 使用 JSON 感知边界：先由 `JSONDecoder.raw_decode()` 确定完整工具对象的结束位置，再校验紧随其后的外层闭合标签。工具参数字符串因此可以原样包含 `<tool_call>`、`</tool_call>` 和 `<final_answer>`。反引号包裹的 action 标签字面量视为普通 reasoning，不参与动作识别。

## Tool

推荐用 `@tool` 标记 Python callable，再由 `CallableTool.from_callable` 构造工具。参数注解与 `ToolArg` 生成 JSON Schema；ToolSet 要求工具名唯一。执行输入为 `ToolCall(name, arguments)`，输出统一为 `ToolResult(name, content, metadata)`。未知工具、参数类型错误和执行异常会转换为明确的 Tool runtime error。

## Lifecycle phases

| phase | 可见 stage key | 用途 |
| --- | --- | --- |
| `pre_prompt` | 无 | 在构造输入前观察持久状态 |
| `post_prompt` | `stage.model_input` | 修改本轮 Model Input |
| `post_model` | `stage.raw_model_output` | 修改解析前文本 |
| `post_parse` | `stage.parser_input`, `stage.parsed_output` | 修改结构化动作 |
| `pre_tool` | `stage.tool_call` | 修改工具调用 |
| `post_tool` | `stage.tool_call`, `stage.tool_result` | 修改工具结果 |
| `pre_final` | `stage.final_decision` | 接受或退回最终回答 |
| `on_error` | `stage.error` | 观察运行错误 |

Hook 构造参数至少包括唯一 `hook_id` 和订阅 `phases`。写 stage 必须声明 `writable_stage_keys`；持久状态通过 `StateRef` 声明 owner、类型、writers 与可选默认值。Hook 的注册顺序就是同一 phase 的执行顺序。

Intervention 分支不会把 Hook State 原样交给 Teacher。运行时把下一次模型调用可见的消息投影为有序 Editable Context Block：`block_id` 使用从 1 开始的数字编号，目录只含类型、角色、长度和短摘要，全文按 ID 单块读取。上下文 patch 只操作这些块；底层 stage 对象、ToolResult metadata 和审计字段继续由 Framework 维护。

## Hook 模型调用

需要辅助模型时，Hook 声明 `model_profiles` 和 `max_model_calls_per_invocation`，通过 `HookContext.call_model()` 调用。`HookModelRequest.thinking_mode` 可取 `enabled` 或 `disabled`，用于覆盖该次调用的 profile 配置；缺省时继承 profile。未授权 profile、超预算、未配置 backend，或 provider 无法表达显式 thinking 覆盖时都会失败并记录 `hook_model_error`。模型调用不得绕开 traced runtime。

Ollama 的 OpenAI-compatible `/v1/chat/completions` 路径以顶层
`reasoning_effort="none"` 表达 `disabled`；`enabled` 省略该字段并使用模型默认 thinking。
Ollama 原生 API 的 `think` 字段不用于这条 OpenAI-compatible 请求路径。DeepSeek 继续使用
其 `thinking.type` 扩展。`thinking_mode` 表示请求控制，实际返回仍应以 response metadata 和
usage 为准。

## FinalDecision

`FinalDecision.accept(answer)` 完成 Agent Run；`FinalDecision.defer(feedback)` 把模型候选回答及反馈追加到 conversation，再进入下一 step。后续 Hook 可以进一步保持 defer，但不能把已有 defer 反转成 accept。

编写实例见[Author a Component](../guides/author-component.md)。
