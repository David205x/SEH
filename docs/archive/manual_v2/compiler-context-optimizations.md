# Compiler 上下文优化

## 文档目的

本文说明新版 Compiler 为降低 Teacher token 消耗、缩短工具轨迹并提高候选实现质量，
依次引入的三项优化：

1. 精简 Compiler system prompt；
2. 程序化 finalizer；
3. 源码驱动 capability packet。

三项优化分别处理不同来源的上下文：

```text
精简 prompt
→ 压缩每轮重复的角色规则和实现约束

程序化 finalizer
→ 移除成功 diff、validation 和 submission 的历史回放

源码驱动 capability packet
→ 移除 API 发现、分页、逐项查询及其累积历史
```

实验采用四类手工构造的复杂 Compiler 需求，每类并行运行三次：

| 场景 | 主要复杂性 |
| --- | --- |
| `post_tool_rewrite` | 两次激活、整数状态、ToolCall/ToolResult 检查、证据和 metadata 保留 |
| `post_prompt_context` | 一次性 ModelInput 替换、消息顺序保持、追加 user message |
| `hook_model_refinement` | 本地 UTF-8 prompt、Hook 内 Student 调用、JSON fallback、ToolResult 重写 |
| `pre_final_semantic` | 自然语言 Actor capability、一次 defer、Actor obligation 和后续放行 |

所有优化都以 Compiler 生成质量为首要门槛。只有候选继续通过 Harness validation、
语义 smoke 和源码质量检查，优化才进入生产模板。

## 一、精简 Compiler Prompt

第一项优化只替换 Compiler system prompt。`CompilerInput`、Parent Harness、工具集合、
API 查询方式和提交工具均保持不变。

### 案例

使用 `post_tool_rewrite`：

> 在 `post_tool` 阶段读取 `ToolCall` 和 `ToolResult`，最多触发两次；保留原始检索
> 内容和 metadata，并附加通用证据检查提示。

实验记录：

```text
runs/components/teacher/mechanism_compilation_validation_01/
  complex_optimization_study/post_tool_rewrite/
    canonical/compiler_run_01.json
    production_prompt_v2/compiler_run_01.json
```

### 修改前上下文

首次模型请求的逻辑结构为：

```text
messages
├─ system: 8,540 字符
│  ├─ 角色和 workspace 边界
│  ├─ Mechanism interpretation
│  ├─ Minimal implementation discipline
│  ├─ 伪代码操作的逐项 lowering 解释
│  ├─ 一次性 pre_final Hook 完整示例
│  ├─ Tool-call efficiency
│  ├─ 8 步 Required procedure
│  ├─ API 白名单解释
│  ├─ requirement-to-code audit
│  ├─ line-level minimality audit
│  └─ validation 和 needs_revision 规则
│
├─ user: 3,706 字符
│  ├─ MechanismSpec
│  ├─ implementation_constraints
│  ├─ validation_feedback
│  └─ Parent Harness 摘要
│
└─ tools
   ├─ 文件读取和写入
   ├─ authoring guide
   ├─ API 浏览和查询
   ├─ diff / validate / submit
   └─ CompilerResult 终止工具
```

旧 prompt 中，同一个原则会以不同形式重复出现。例如“只实现机制要求的行为”
分别出现在：

```text
Minimal implementation discipline
→ requirement-to-code audit
→ line-level minimality audit
→ validation 前检查
```

API 使用规则也有多层重复：

```text
读取 authoring guide
→ list API
→ query 每个 API
→ 不得猜测 API
→ stable API 不要动态探测
→ open API 不要猜测字段
```

这些规则本身正确，但 system prompt、工具 docstring、authoring guide 和 API 查询
结果重复表达了相同内容。

### 修改后上下文

精简后的结构为：

```text
messages
├─ system: 4,422 字符
│  ├─ 角色和只读 Parent 边界
│  ├─ 集中的机制解释原则
│  ├─ 成本敏感执行流程
│  ├─ minimal lowering rules
│  ├─ factory 和异常处理规则
│  └─ 一份提交前检查清单
│
├─ user: 3,706 字符       ← 不变
└─ tools                  ← 不变
```

核心变化不是删除约束，而是合并表达：

| 修改前 | 修改后 |
| --- | --- |
| 三组不同层级的最小性审查 | 一份提交前 checklist |
| 反复解释伪代码不能直接映射 API | 一条权威解释原则 |
| 通用 Hook 生命周期长篇说明 | 交给 authoring guide |
| 每种状态操作分别展开 | 集中为 lowering rules |
| 默认读取所有可能相关组件 | 只读取机制依赖或会修改的组件 |
| 多处禁止反射和猜测接口 | 统一放入 API 和 factory 边界 |
| 完整展示常见状态机实现 | 只保留实现所需的行为约束 |

例如旧版接近：

```text
建立 requirement-to-code map。
检查每一个 branch。
检查每一个 state field。
检查每一个 temporary variable。
检查每一个 helper。
再做 line-level minimality audit。
```

精简后合并为：

```text
Before validation, verify:
- every implementation constraint is represented;
- activation state and repeated activation are correct;
- every state write has permission;
- no redundant phase check, read, rewrite or dummy statement exists.
```

### 保留的信息

以下约束没有因为精简而丢失：

- `behavioral_pseudocode` 是控制流权威来源；
- Hook 行为和 Actor obligation 必须分开；
- Parent Harness 和 fixed 组件只读；
- 不允许反射和未公开 API；
- 必须执行 activation budget；
- `StateRef.writers` 和 stage 写权限必须正确；
- factory 必须处理未知配置；
- 禁止宽泛异常捕获和 dummy statement；
- 普通 validation error 应在当前 run 修复；
- 只有机制规格不足时才能返回 `needs_revision`。

### 实际效果

system prompt 长度：

```text
8,540 chars → 4,422 chars
下降 48.2%
```

同一案例首轮 prompt token：

```text
3,823 → 3,021
下降约 21.0%
```

三类复杂需求的总 token 均值：

```text
旧 canonical：191,610
精简 prompt： 144,519
下降 24.6%
```

质量结果：

```text
语义 smoke：
旧版      9/9
精简版    9/9

源码质量检查：
旧版      71/84
精简版    74/84
```

### 边界

精简 prompt 只降低每轮都会携带的静态 system message。它没有减少 API 查询、文件
回读、diff 和 validation 产生的动态历史，因此不能单独解决 Compiler 轨迹持续
增长的问题。

## 二、程序化 Finalizer

第二项优化在精简 prompt 基础上，将模型原本负责的 diff、validation 和 candidate
submission 合并为一个程序事务。

### 修改前上下文

Compiler 写完代码后，需要依次调用：

```text
write_candidate_file
→ show_candidate_diff
→ validate_candidate
→ submit_candidate
→ submit_compiler_result
```

在 `post_tool_rewrite` 案例中：

```text
assistant:
  调用 show_candidate_diff

tool:
  返回完整 diff
  包括新增 Python 文件和 harness.json
  共 3,032 字符

assistant:
  检查 diff，调用 validate_candidate

tool:
  返回完整 validation report
  共 274 字符

assistant:
  调用 submit_candidate

tool:
  返回 candidate_ref、digest 和 changed_paths
  共 196 字符

assistant:
  提交最终 CompilerResult
```

Chat Completions 的后续请求会重新携带前面的历史：

```text
调用 validate_candidate：
  上下文包含完整 diff

调用 submit_candidate：
  上下文包含完整 diff + validation

提交 CompilerResult：
  上下文包含完整 diff + validation + submit result
```

仅这个案例，提交阶段累计重复携带约：

```text
diff:       3,032 × 3
validation:   274 × 2
submit:       196 × 1
--------------------
约 9,840 字符
```

Hook-model 案例的完整 diff 达到 `5,642` 字符，因此候选越复杂，重复历史越大。

工具 schema 也会在每轮携带：

```text
show_candidate_diff
validate_candidate
submit_candidate
```

### 修改后上下文

三个工具被合并为：

```text
write_candidate_file
→ finalize_candidate
→ submit_compiler_result
```

模型调用：

```json
{
  "summary": "Add a two-activation post-tool evidence review Hook."
}
```

程序内部执行：

```text
计算完整 diff
→ 执行 Compiler 专属源码审查
→ 执行 HarnessValidator
→ 绑定当前 revision 和 digest
→ 冻结 candidate
```

成功后，模型只看到紧凑结果：

```json
{
  "status": "submitted",
  "candidate_ref": "candidate_001",
  "candidate_digest": "...",
  "changed_paths": [
    "extensions/search_evidence_review/plugin.py",
    "harness.json"
  ],
  "validation_passed": true
}
```

成功字段职责：

| 字段 | 含义 |
| --- | --- |
| `status` | 表示候选已经提交 |
| `candidate_ref` | 当前 Teacher run 内已冻结候选的稳定引用 |
| `candidate_digest` | 绑定候选准确文件内容，防止 revision 混淆 |
| `changed_paths` | 表示本次事务包含的文件 |
| `validation_passed` | 表示程序侧确定性门禁已经通过 |

完整 diff 没有被丢弃，而是从模型上下文移动到审计 artifact：

```text
resource_artifacts.compiler_candidate
├─ diff
├─ validation
├─ changed_files
├─ parent_digest
├─ candidate_digest
└─ revision
```

由此区分：

```text
模型决策上下文：
  只保留是否成功、候选引用和修复错误

程序审计 artifact：
  保存完整 diff、源码、validation 和 digest
```

### 失败时

如果程序检查失败，finalizer 不提交候选，只返回修复需要的信息：

```json
{
  "status": "repair_required",
  "revision": 2,
  "candidate_digest": "...",
  "changed_paths": [
    "extensions/evidence_planner/plugin.py",
    "harness.json"
  ],
  "errors": [
    "stage.model_input must be checked with isinstance(..., ModelInput)"
  ]
}
```

失败字段职责：

| 字段 | 含义 |
| --- | --- |
| `status` | 明确要求模型继续修复，而不是结束 Compiler |
| `revision` | 指明错误对应的 workspace revision |
| `candidate_digest` | 标识发生错误的准确候选内容 |
| `changed_paths` | 限定当前事务中的变更文件 |
| `errors` | 给出下一步可直接执行的确定性修复要求 |

模型在同一 run 内继续：

```text
finalize_candidate
→ repair_required
→ write_candidate_file
→ finalize_candidate
→ submitted
```

不需要重新查看成功 diff，也不需要分别调用 validation 和 submit。

### 程序侧源码审查

finalizer 还增加了 Compiler 专属机械检查：

```text
禁止 del config / del context
禁止 except Exception / BaseException
factory 必须验证或使用 config
访问可空 stage 值前必须显式 isinstance
```

这些检查只作用于 Compiler 改动的 Python 文件，不扩张通用 Version Store validator
的职责。

### 实际效果

| 场景 | Finalizer 前 | Finalizer 后 | 变化 |
| --- | ---: | ---: | ---: |
| Post-tool rewrite | 142,495 | 91,848 | -35.5% |
| Post-prompt context | 111,459 | 91,634 | -17.8% |
| Hook-model refinement | 179,602 | 225,207 | +25.4% |
| 整体均值 | 144,519 | 136,230 | -5.7% |

源码质量：

```text
精简 prompt：     74/84
加入 finalizer： 84/84
```

Hook-model 场景 token 上升，是因为更严格的审查触发了额外修复轮。由此可见，
finalizer 的第一目标是候选质量和事务一致性，而不是保证每个复杂机制都单独降低
token。

### 边界

finalizer 证明的是：

- 当前 revision 的 diff、manifest、语法、导入和装配合法；
- Compiler 专属机械规范通过；
- `candidate_ref` 对应准确的已校验文件内容。

finalizer 不证明：

- 代码与自然语言机制完全语义等价；
- Actor 一定遵循 Hook feedback；
- 候选能提高任务准确率。

这些仍由语义 smoke、candidate rollout、evaluation 和 Candidate Reviewer 验证。

## 三、源码驱动 Capability Packet

第三项优化把模型运行时逐项探索 API 的过程，改为程序在模型调用前根据机制一次性
选择所需能力。

其本质是：

```text
动态检索和累积 API 历史
→ 预编译、phase-scoped 的精确上下文
```

### 修改前上下文

在 `post_tool_rewrite` 案例中，Compiler 首轮上下文较小：

```text
system prompt：4,718 字符
user input：   3,706 字符
首轮 prompt：  2,987 tokens
```

但模型需要运行时探索：

```text
list_harness_files
→ get_hook_authoring_guide("implementation")
→ read_harness_file("harness.json")
→ get_hook_authoring_guide("lifecycle")
→ get_hook_authoring_guide("state_access")
→ get_hook_authoring_guide("manifest")
→ query_hook_api("BaseHook")
→ query_hook_api("HookContext")
→ query_hook_api("HookPhase.POST_TOOL")
→ query_hook_api("StateRef")
→ query_hook_api("HookStateView.get")
→ query_hook_api("HookStateView.set")
→ query_hook_api("stage.tool_call")
→ query_hook_api("stage.tool_result")
→ query_hook_api("ToolCall")
→ query_hook_api("ToolResult")
→ 写入候选
```

该次运行发生：

```text
authoring guide 调用： 6 次
API 精确查询：       10 次
API 探索工具调用：   16 次
唯一返回文本：        11,914 字符
```

返回内容进入对话历史后逐步累积：

```text
请求 1：初始任务
请求 2：初始任务 + guide 1
请求 3：初始任务 + guide 1 + guide 2
...
请求 9：初始任务 + 全部 guide + 前几个 API
请求 11：初始任务 + 全部 guide + 全部 API + 候选历史
```

最终：

```text
模型请求：11 次
工具调用：25 次
总 token：107,123
```

### Packet 生成

程序读取 `MechanismSpec`：

```text
trigger_phase = post_tool

decision_inputs:
- stage.tool_call
- stage.tool_result
- extension result-rewrite count

required_capabilities:
- ToolCall
- ToolResult
- StateRef
- HookStateView.get
- HookStateView.set
- stage.tool_call
- stage.tool_result
```

然后从当前源码和 Hook API catalog 中，只选择本机制需要的 10 个契约：

```text
BaseHook
HookContext
StateRef
HookStateView.get
HookStateView.set
HookPhase.POST_TOOL
stage.tool_call
stage.tool_result
ToolCall
ToolResult
```

不会携带：

```text
HookPhase.PRE_FINAL
FinalDecision
HookPhase.POST_PROMPT
ModelInput
ChatMessage
ParsedOutput
HookModelRequest
HookContext.call_model
其他 phase 的 stage 值
```

该案例的 compact packet 约 `7,293` 字符。

### Packet 结构

模型收到的结构近似：

```json
{
  "packet_version": 2,
  "catalog_versions": {
    "hook_api": 1,
    "authoring_guide": 4
  },
  "selection": {
    "strategy": "phase_scoped_exact",
    "trigger_phase": "post_tool",
    "decision_evaluator": "deterministic",
    "activation_budget": 2,
    "exact_decision_inputs": [
      "stage.tool_call",
      "stage.tool_result"
    ],
    "semantic_decision_inputs": [
      "extension result-rewrite count"
    ],
    "unresolved_api_capabilities": [],
    "unresolved_symbols": []
  },
  "contracts": [
    "...10 个源码驱动契约..."
  ],
  "authoring": {
    "factory_rules": ["..."],
    "state_namespaces": ["..."],
    "state_rules": ["..."],
    "manifest_changes": ["..."],
    "manifest_rules": ["..."],
    "compiler_review_rules": ["..."]
  }
}
```

顶层字段职责：

| 字段 | 含义 |
| --- | --- |
| `packet_version` | 标识 packet 自身的结构版本 |
| `catalog_versions` | 记录生成时使用的 Hook API 和 authoring guide 版本 |
| `selection` | 解释程序为什么选择这些契约，以及是否存在未解析能力 |
| `contracts` | 提供当前机制可用类型、方法、字段和状态键的精确契约 |
| `authoring` | 提供 factory、state、manifest、模型调用和源码审查规则 |

当 packet 包含 Hook-model 能力时，`authoring` 额外提供
`allowed_model_profiles`。当前值为 `student`；Compiler 必须从该列表选择
profile，不能自行猜测模型角色。上面的确定性 post-tool 示例不包含该字段。

`selection` 字段职责：

| 字段 | 含义 |
| --- | --- |
| `trigger_phase` | 本次机制注册的 Hook phase |
| `decision_evaluator` | 触发判断使用确定性规则还是有界 Hook 小模型 |
| `activation_budget` | 单次 rollout 允许的最大激活次数 |
| `exact_decision_inputs` | 可直接映射到框架状态键的输入 |
| `semantic_decision_inputs` | 机制需要理解、但不应猜测为 API 的语义信息 |
| `exact_required_capabilities` | 已解析的公开 API 符号 |
| `semantic_required_capabilities` | Actor 行为能力，不视为框架接口 |
| `unresolved_api_capabilities` | 看起来是 API、但 catalog 无法解析的明确缺口 |
| `unresolved_symbols` | packet 选择过程中未找到的内部符号 |

### 源码驱动

Packet 不是由模型凭记忆生成，也不是手写 API 摘要。其信息来自当前实现：

```text
公开类和方法签名
→ Python inspect / type hints / docstring

Hook phase 和 stage key
→ STAGE_KEYS_BY_PHASE

StateRef 和状态权限
→ 当前 Hook state 实现

authoring 规则
→ hook_authoring.py

公开范围
→ hook_api.py 白名单
```

框架 API 变化后，packet 会根据当前源码重新生成，不需要同步维护另一份长 prompt。

### 契约压缩方法

#### 按 phase 裁剪

```text
post_tool
→ HookPhase.POST_TOOL
→ stage.tool_call
→ stage.tool_result
→ ToolCall
→ ToolResult
```

不会包含其他 phase。

#### 按成员裁剪

`BaseHook` 默认只保留：

```text
hook_id
phases
state_refs
writable_stage_keys
handle
```

`decision_evaluator=hook_model` 或机制显式要求其他 Hook-model 行为时，才增加：

```text
model_profiles
max_model_calls_per_invocation
HookContext.call_model
HookModelRequest
HookModelResponse
```

触发判断的模型能力由结构化 `decision_evaluator` 直接选择，不再依赖 Compiler
从自然语言中猜测；非触发判断用途的模型调用仍需在机制能力中显式声明。

#### 去除重复元数据

每个契约中重复的内容会被删除：

```text
catalog_version
generated_from_source
owner
重复 summary
空字段
```

catalog 版本只在 packet 顶层记录一次。

#### 区分语义和 API

例如：

```text
Actor can follow a generic continuation instruction
```

属于 Actor 行为约束，不会被错误地拿去查询 API。

而：

```text
FinalDecision.defer
```

属于精确 API，会被解析成源码契约。

### 修改后上下文

首轮 user context 因加入 packet 而变大：

```text
修改前 user context： 3,706 字符
修改后 user context：14,788 字符

修改前首轮 prompt：2,987 tokens
修改后首轮 prompt：5,086 tokens
```

但后续不再产生 API 探索历史：

```text
修改前：
16 次 API/guide 调用
11,914 字符唯一返回内容
11 次模型请求
25 次总工具调用

修改后：
0 次 API/guide 调用
0 字符 API 查询返回
6 次模型请求
8 次总工具调用
```

修改后的轨迹为：

```text
list_harness_files
→ read_harness_file
→ read_harness_file
→ read_harness_file
→ write_candidate_file
→ write_candidate_file
→ finalize_candidate
→ submit_compiler_result
```

因此 capability packet 不是把首轮 prompt 变小，而是：

```text
首轮携带一份稍大的精准知识包
→ 消除多轮发现、查询、返回和历史回放
→ 缩短整个 Compiler 轨迹
```

### 不同机制的 Packet 大小

| 场景 | 契约数 | Compact packet |
| --- | ---: | ---: |
| Post-tool rewrite | 10 | 7,293 字符 |
| Post-prompt context | 10 | 7,072 字符 |
| Hook-model refinement | 19 | 11,274 字符 |
| Pre-final semantic | 9 | 6,987 字符 |

Hook-model packet 更大，因为它确实需要：

```text
ChatMessage
ModelInput
HookModelRequest
HookModelResponse
HookContext.call_model
模型 profile 和调用预算
JSON 解析方法
model inference authoring rules
```

### 实际效果

相较“精简 prompt + finalizer，但仍动态查询 API”：

| 场景 | Packet 前 | Packet 后 | 变化 |
| --- | ---: | ---: | ---: |
| Post-tool rewrite | 91,848 | 65,855 | -28.3% |
| Post-prompt context | 91,634 | 51,577 | -43.7% |
| Hook-model refinement | 225,207 | 134,132 | -40.4% |
| 三类均值 | 136,230 | 83,855 | -38.4% |

质量保持：

```text
语义 smoke：9/9
源码质量：  84/84
```

首次 finalization：

```text
Packet 前：3/9
Packet 后：8/9
```

这说明 packet 不只减少 token，也让 Compiler 在第一次写代码前就拥有更完整、准确
的 API 约束。

### 边界

Packet 只提供公开框架能力，不替代机制语义：

- `behavioral_pseudocode` 仍决定控制流；
- `prohibited_behaviors` 仍决定安全边界；
- `implementation_constraints` 仍决定本次实现的具体要求；
- packet 不判断 intervention 是否有效；
- packet 不推断未声明的语义谓词；
- 无法解析且实现必需的精确 API 会导致 `needs_revision`。

## 四、组合效果

最终生产组合为：

```text
精简 prompt
+ 程序化 finalizer
+ 源码驱动 capability packet
```

三类可直接对照的复杂需求：

```text
旧 canonical：191,610 tokens
最终生产版：   83,855 tokens
下降 56.2%
```

四类最终复杂机制共十二次 Teacher 运行：

```text
候选提交：             12/12
Harness validation：  12/12
语义 smoke：           12/12
源码质量检查：         105/105
首次 finalization：   11/12
```

唯一一次修复由 finalizer 捕获 `del context`，模型在同一 run 中修复后正常提交。

三项机制的最终职责边界：

| 机制 | 负责的信息 |
| --- | --- |
| 精简 prompt | 角色语义、机制解释、实现流程和安全约束 |
| Capability packet | 当前机制所需的源码驱动公开 API |
| 程序化 finalizer | 源码审查、Harness 校验和准确 revision 提交 |

## 五、实现与实验位置

当前实现：

```text
search_harness/teacher/compiler_capabilities.py
search_harness/teacher/compiler_review.py
search_harness/teacher/role_resources.py
search_harness/teacher/builtin_tools.py
harness_templates/teacher/compiler/plugins/harness.json
harness_templates/teacher/compiler/plugins/prompts/compiler/templates/system.md
```

实验工具：

```text
experiments/build_complex_compiler_requests.py
experiments/run_complex_compiler_matrix.py
experiments/evaluate_complex_compiler_matrix.py
```

最终实验结果：

```text
runs/components/teacher/mechanism_compilation_validation_01/
  complex_optimization_study/production_packet_final_evaluation.json
  complex_compiler_optimization_report.md
```
