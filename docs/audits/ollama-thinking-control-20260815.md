# Ollama OpenAI-compatible Thinking 控制验证

## 结论

当前框架原先没有在 Ollama 的 OpenAI-compatible `/v1/chat/completions` 路径正确关闭
thinking。配置中的 `thinking_mode: disabled` 被映射成 Ollama 原生 API 字段
`think: false`，但本机 `/v1` endpoint 忽略该字段。修复后，Ollama `disabled` 映射为顶层
`reasoning_effort: "none"`；`enabled` 省略该字段并使用模型默认 thinking。DeepSeek 的
`thinking.type` 路径没有改变。

修复同时覆盖普通 `OpenAICompatibleModel`、Hook Model/Student Model Experiment、同步
`OpenAICompatibleToolSession` 和普通 Teacher Role 使用的异步 native tool runner。

## 实验设计

- Endpoint：`http://127.0.0.1:11434/v1`
- Model：`qwen3:8b`
- `temperature=0`、`seed=42`、`max_tokens=256`
- 案例：一个算术终答和一个 Hook 风格三值分类输入
- 每种请求方式、每个案例重复 3 次，共 24 次普通生成
- 另用修复后的 `OpenAICompatibleToolSession` 重复 3 次 structured tool calling
- 完整 observation 保存在
  `runs/experiments/ollama_thinking_control_20260815/results.json`

## 普通生成结果

| 请求方式 | 调用 | 含 reasoning | 含正文 | 总 token | 平均耗时/秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 修复后框架 `disabled` | 6 | 0 | 6 | 666 | 0.681 |
| SDK `reasoning_effort="none"` | 6 | 0 | 6 | 666 | 1.134 |
| 旧 `think: false` | 6 | 6 | 0 | 1965 | 2.581 |
| 框架 `enabled`/模型默认 | 6 | 6 | 0 | 1965 | 3.056 |

修复后的框架输出、usage 和 reasoning 可见性与 SDK 原生参数逐次一致。相对旧字段，当前
样本总 token 降低约 66.1%；旧字段与 enabled 对照都在 256 token 上限内只生成 reasoning，
没有形成正文。该比例只描述本次短输入，不外推为其他任务的固定成本收益。

算术案例两条 disabled 路径均为 3/3 正确。Hook 分类案例两条路径均稳定输出
`uncertain`，而实验预置 fragment 为 `positive`；这说明传输控制完全一致，不表示关闭
thinking 会自动保持所有语义任务的标签质量。Hook Model 的行为边界仍需由 Teacher 使用
描述性 Student Model Experiment 观察，不能恢复 expected-label 硬门禁。

## Structured tool calling

修复后的 `OpenAICompatibleToolSession` 在 3/3 重复中均产生一个合法 `echo` tool call，
参数均为 `{"value": "313"}`，reasoning 长度均为 0，每次总 token 为 178。关闭 thinking
没有破坏本机 Qwen 的原生工具调用结构。

最后直接通过项目 `.env + config/runtime.yaml` 加载正式 `STUDENT` profile 做 smoke：实际
请求包含 `reasoning_effort: "none"` 且不含 `think`，模型返回 `READY`，reasoning 长度为
0，总 token 为 24。这确认配置投影、provider 映射和普通生成链路已经连通。

## 边界

- `thinking_mode` 是框架逻辑设置；Ollama `/v1` 和 DeepSeek 使用不同的请求字段。
- Ollama `enabled` 当前表示恢复模型默认 thinking，不强制选择 low/medium/high effort。
- 模型输出质量、标签稳定性和成本仍需按具体 prompt 观察，不能只根据请求字段推断。
