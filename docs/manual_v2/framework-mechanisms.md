# 框架机制设计

## 文档职责

本文档记录框架层中跨角色、跨 Harness 实例复用的机制设计及其稳定边界。具体
Actor plugin 的目录、manifest、factory 和 Hook phase 协议见
[Harness Plugins](harness-plugins.md)；新版 Compiler 如何使用这些机制见
[Compiler](compiler.md)。

当前首先记录新版 Compiler 使用的源码驱动 Hook API 目录。该目录解决的是
“模型如何准确理解框架接口”，不是新的 Hook runtime，也不改变 Actor loop 的行为。

## Hook API 目录的目标

Compiler 编写 Hook 时需要同时知道两类信息：

- **当前代码事实**：类是否存在、构造签名、字段类型、方法签名和 docstring；
- **框架语义承诺**：哪些接口允许插件依赖、稳定程度如何、容器形状是否封闭。

只把完整源码交给模型会暴露大量内部实现，并迫使模型自行判断哪些成员可依赖；
只维护一份手写 API 文档又容易与代码漂移。因此，当前实现把 API 说明分为四层：

1. `search_harness/core/` 是运行行为、类型签名和 docstring 的事实来源；
2. `search_harness/teacher/hook_api.py` 使用显式白名单定义 Compiler 可见边界；
3. 同一目录为公开项补充稳定性、形状和必要语义说明；
4. Compiler 通过分页发现与精确查询工具按需读取，不把整份说明塞入 system prompt。

这套设计只接入新版 `search_harness.teacher` Compiler。旧版
`search_harness.adapter.compiler` 不属于该接口的维护范围。

## 公开白名单

API 目录不会扫描模块后自动公开所有 Python 对象。只有白名单中的类、字段、方法、
枚举值、Hook phase 和状态键可被查询。

当前对象分类包括：

| 分类 | 主要公开对象 |
| --- | --- |
| `hook` | `BaseHook`、`HookContext`、`HookPhase` |
| `state` | `HookStateView`、`StateRef` |
| `message` | `ChatMessage`、`ModelInput` |
| `model` | `HookModelRequest`、`HookModelResponse` |
| `tool` | `ToolCall`、`ToolResult` |
| `parser` | `ParsedOutputKind`、`ParsedOutput` |
| `final` | `FinalDecisionAction`、`FinalDecision` |
| `trace` | `TraceEvent` |
| `stage` | `stage.*` phase-local 状态键 |
| `core` | 允许 Hook 读取的 `core.*` 投影 |

私有成员默认隐藏。例如 `HookContext._model_backend` 即使真实存在，也不属于
Compiler-facing contract。公开类上未列入白名单的方法同样不可依赖。这样可以让
core 自由调整内部实现，而不把 Python 反射结果误当成插件协议。

`HookStateView` 是一个特殊公开项：Compiler 可以查询它的 `get` 和 `set` 签名，
但插件不应构造或直接导入该类型；它只通过 `HookContext.state` 由 runtime 提供。

## 源码驱动与显式语义

以下内容从当前源码动态生成：

- dataclass 构造签名；
- 公开字段的 type hint 和默认值；
- 公开方法签名；
- 类与方法 docstring；
- 枚举和 `HookPhase` 常量值；
- `stage.*` 对应的实际 Hook phase。

以下内容不能从 Python 结构可靠推断，因此由白名单策略显式维护：

- 是否允许 Compiler 使用；
- `stable` 或 `experimental`；
- `closed` 或 `open`；
- 状态键的生命周期、写入效果和使用备注；
- 某些运行时对象是否允许直接导入或构造。

因此，签名变化通常不需要手工同步文档；语义承诺变化仍必须显式评审并更新目录。

## 稳定性与形状

稳定性和形状是互相独立的两个维度。

### 稳定性

| 值 | 含义 |
| --- | --- |
| `stable` | Compiler 可以依赖文档中的签名和语义；框架修改它时应视为插件协议变更。 |
| `experimental` | 当前可以使用，但 Compiler 必须查询精确成员，不能推断未说明的兼容行为。 |

### 形状

| 值 | 含义 |
| --- | --- |
| `closed` | 已列出的字段、枚举值或结构就是完整契约。 |
| `open` | 容器可包含工具、provider 或具体组件附加的数据，只能检查机制真正需要的内容。 |

例如 `ToolResult` 本身是 `stable + closed`：`name`、`content` 和 `metadata` 是确定
字段；`ToolResult.metadata` 则是 `stable + open`，因为其中键值由具体工具定义。

`stable/experimental` 与 Harness manifest 中的 `fixed/mutable` 不是同一个概念。
前者描述框架 API 承诺，后者描述某个 Harness 组件是否允许被演化修改。

## 状态键目录

状态键不是 Python 对象属性，因此单独作为 API symbol 暴露。

`stage.*` 查询会返回：

- 当前值的精确类型；
- 可用的 Hook phase；
- 读取与写入方式；
- 写入发生时是否仍会影响主流程；
- 稳定性与形状。

例如：

```text
query_hook_api("stage.tool_result")
```

会说明它只在 `post_tool` 可用、类型为 `ToolResult`，并在该 phase 后写入 Actor
历史。

`core.*` 查询描述的是 `AgentState.to_dict()` 的只读投影，而不是可修改的
`AgentState` 对象。`core.question`、`core.step` 和 `core.max_steps` 是稳定闭合值；
历史列表和 `core.hook_state` 当前标记为开放或实验性投影。插件不能写入 `core.*`。

## 渐进式查询

Compiler 使用两类工具读取目录：

```text
list_hook_api_symbols(category="tool", page=1, page_size=20)
query_hook_api(symbol="ToolResult.metadata")
```

`list_hook_api_symbols` 只提供查询入口、分类、摘要和分页信息；
`query_hook_api` 才返回一个类、成员或状态键的精确契约。支持的查询形式包括：

```text
BaseHook
BaseHook.model_profiles
HookContext.call_model
HookPhase.POST_TOOL
FinalDecisionAction.DEFER
ToolResult.metadata
stage.tool_result
core.question
```

该接口不会接受任意 dotted import，也不会让模型通过查询工具读取函数体。模型只能
访问框架维护者明确选择的公开表面。

## Authoring Guide 与 API Catalog

二者职责不同：

- Authoring Guide 解释生命周期、跨 phase 状态、模型调用、终答控制和 manifest
  等“应该怎样组合机制”；
- API Catalog 回答“当前代码中准确存在什么，签名和稳定性是什么”。

Compiler 应先读取 guide 的 `index` 和相关主题，再列出 API 分类，并精确查询本次
实现实际使用的每一个类、成员和状态键。guide 不再重复维护大段字段表。

## 维护规则

修改 Compiler-facing Hook API 时应遵守：

1. 行为、type hint 与 docstring 在 `search_harness/core/` 中维护；
2. 新公开项必须显式加入白名单，不允许自动泄露整个模块；
3. 新增或改变语义承诺时同步设置稳定性、形状和说明；
4. 私有实现优先不公开；确需解释时只公开必要签名与使用备注；
5. 为查询结果补充测试，至少覆盖动态签名、私有成员隐藏和状态 phase；
6. 更新 Compiler prompt 时只强调查询流程，不复制完整 API 内容。

当前实现文件：

```text
search_harness/teacher/hook_api.py
search_harness/teacher/hook_authoring.py
search_harness/teacher/builtin_tools.py
search_harness/teacher/role_resources.py
harness_templates/teacher/compiler/plugins/
```

## 当前边界

- 目录只服务于新版 Compiler，不是面向任意外部 Python 调用方的反射服务。
- 目录自动同步签名和 docstring，但稳定性与行为备注仍需人工维护。
- 当前只覆盖 Hook authoring 所需的最小公开表面，不覆盖 `AgentLoop`、
  `HookPipeline`、registry 和 validator 的内部 API。
- 查询工具提高接口正确性，但候选是否可运行仍由 `validate_candidate` 决定。
- 当前校验不包含数据集 rollout；候选效果由后续评估和 Candidate Reviewer 判断。
