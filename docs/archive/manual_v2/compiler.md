# Compiler

## 文档职责

本文描述新版 Teacher Compiler 的当前实现。角色分工见
[Teacher 角色定义](teacher-roles.md)，Teacher 调用后端见
[Teacher Runtime](teacher-runtime.md)。三项上下文优化的修改前后对照和实验数据见
[Compiler 上下文优化](compiler-context-optimizations.md)。

Compiler 将一个已验证、无需在线 Teacher 的 `MechanismSpec` 翻译成最小 Actor
Harness plugin 候选。它负责实现和确定性合法性，不负责证明策略有效，也不负责
接受新版本。

## 设计边界

Compiler 负责：

- 读取 Parent Harness 的 manifest 和必要源码；
- 使用程序提供的 capability packet 理解本次可用 Hook API；
- 在 run-local 内存 workspace 中新建、修改或删除 mutable 文件；
- 根据程序化 finalizer 的错误反馈修复实现；
- 提交一个绑定到准确 revision 和 digest 的 `candidate_ref`；
- 报告实现摘要和仍需下游验证的风险。

Compiler 不负责：

- 修改只读 Parent Harness 或 fixed 组件；
- 重新判断 intervention 是否有效；
- 决定 candidate 是否进入 checkpoint store；
- 猜测 packet 未公开的 runtime API；
- 把 Teacher 调用、题目答案或具体案例事实固化进 Actor Harness。

## 分层

| 层 | 当前实现 | 职责 |
| --- | --- | --- |
| Template | `harness_templates/teacher/compiler/plugins/` | 声明角色、固定工具和精简 prompt |
| Contract | `search_harness/teacher/contracts.py` | 绑定 `CompilerInput` 与 `CompilerResult` |
| Capability | `compiler_capabilities.py` | 从机制和当前源码目录生成本次 API packet |
| Resource | `CompilerWorkspaceStore` | 管理 Parent Snapshot、候选 revision、审查和提交 |
| Runtime | `NativeChatTeacherRuntime` | 执行原生 tool calling 并校验结构化终态 |

这五层分别承担语义输入、API 知识、文件事务和模型执行，避免把全部职责重复写进
system prompt。

## 输入协议

`CompilerInput`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `mechanism` | `MechanismSpec` | 已由上游验证的 Teacher-free 机制 |
| `implementation_constraints` | `list[str]` | 本次实现必须满足的额外约束 |
| `validation_feedback` | `list[str]` | 前一轮编译或校验产生的定向反馈 |

`MechanismSpec` 中与编译最相关的字段：

| 字段 | 含义 |
| --- | --- |
| `goal` | 机制希望改变的 Actor 行为 |
| `phase_rules` | 一至四条有因果关系的 phase 局部规则 |
| `phase_rules[].phase` | 当前规则进入的 Hook phase |
| `phase_rules[].trigger_condition` | 当前 phase 何时激活 |
| `phase_rules[].decision_inputs` | 当前规则允许读取的信息 |
| `phase_rules[].decision_evaluator` | 当前规则由确定性逻辑还是有界 Hook 小模型判断 |
| `phase_rules[].action` | 当前 phase 的主要干预动作 |
| `phase_rules[].activation_budget` | 当前 phase 在单次 rollout 中的独立激活上限 |
| `behavioral_pseudocode` | 控制流、状态变化、Actor 交接和 fallback 的权威描述 |
| `state_scope` | 状态变量的生命周期 |
| `fallback` | 不确定或异常分支的安全行为 |
| `required_capabilities` | 实现所需的公开 Hook 能力 |
| `prohibited_behaviors` | 候选不得实施的行为 |

自然语言字段约束目标和边界，`behavioral_pseudocode` 约束行为顺序。伪代码中的
Actor obligation 应实现为给 Actor 的反馈，不能被误写成 Hook 自己执行搜索或推理。

## Capability Packet

`TeacherResources.bind_role_input()` 在 `CompilerInput` 校验后，调用
`build_compiler_capability_packet()` 生成只读能力包并放入 Compiler user prompt。

能力包由程序维护，不是模型输出协议：

| 字段 | 含义 |
| --- | --- |
| `packet_version` | 能力包结构版本 |
| `catalog_versions` | 生成时使用的 Hook API 和 authoring guide 版本 |
| `selection` | 每条 phase rule 的 evaluator、预算、已解析输入及全局未解析能力 |
| `contracts` | 本次可使用的公开类型、方法、状态键和写入规则 |
| `authoring` | factory、state、manifest、模型调用和代码审查规则 |

选择策略：

1. 总是包含 `BaseHook`、`HookContext`、`StateRef` 和状态读写接口；
2. 遍历 `phase_rules`，合并所有对应 phase、stage 值及值类型；
3. 按 rule 加入 `decision_inputs` 中精确的 `core.*`、`stage.*` 契约；
4. 解析 `required_capabilities` 中可直接查询的公开符号；
5. 任一 rule 使用 `decision_evaluator=hook_model` 时加入模型调用契约和
   authoring 规则，同时保留其他 rule 的确定性边界；
6. 已确认的常见语义输入使用显式映射；当前
   `conversation_history` 映射为 `HookContext.trace` 与 `TraceEvent`；
7. 没有映射的语义输入仍保留为语义，不猜测成框架 API；
8. 自然语言 Actor 能力保留为语义约束，不被误判为缺失 API；
9. 非触发判断用途的 Hook-model 能力仍由显式 capability 描述按需加入；
10. packet 确实遗漏实现关键符号时，Compiler 可在硬预算内精确查询；
11. 精确 API 仍无法解析时，由 Compiler 返回 `needs_revision`。

Compiler 必须逐 rule 服从 evaluator 边界：`deterministic` 不得擅自增加模型
调用，也不得使用新造的关键词、正则或分数近似开放语义判断；`hook_model`
必须使用 packet 提供的 `HookContext.call_model` 等公开接口，不得退化成短语
匹配。若某条 rule 的 evaluator 与触发条件、伪代码或证据边界冲突，应返回
`needs_revision` 并指出具体 phase。
模型能力出现时，packet 还会通过 `authoring.allowed_model_profiles` 列出可用
profile；当前 Actor 装配只允许 `student`，Compiler 不应猜测或写入其他角色。

Compiler template 不注册 API 列表和 authoring guide 工具。packet 是主要公开
API 边界；`query_hook_api` 只是 packet 缺口的 exact-query 逃生口。每次 run
最多查询 4 个唯一符号，未知符号也消耗预算；packet 已包含、已经查询或超过预算
的请求只返回简短拒绝原因，不重复返回契约。

多 phase 机制可以由一个订阅多个 phase 的 Hook 实现，也可以由同一个
extension 返回多个 Hook。跨 phase 交接必须使用 manifest 已声明的
`extension.*` 或 `shared.*` 状态；每条 rule 的预算单独执行。Compiler 在新增
组件前会先读取现有 mutable extension；当修改现有实例是最小完整实现时，允许
直接修改它，fixed 组件仍不可变。

## Candidate Workspace

Compiler 启动时从 Parent plugins root 创建 `HarnessSnapshot` 和
`CandidateWorkspace`。Parent 保持只读，所有文件工具只修改内存候选。

workspace 规则：

1. 每次写入或删除都会递增 revision；
2. 任意变更都会清除旧 validation；
3. fixed 边界由 `HarnessValidator` 检查；
4. 没有文件变化的候选不能提交；
5. 提交绑定准确 revision、parent digest 和 candidate digest；
6. 提交产物保存在 Teacher artifact，不直接写回 checkpoint store。

## 工具

Compiler 当前注册六个固定工具：

| 工具 | 用途 |
| --- | --- |
| `list_harness_files` | 查看当前候选文件目录和大小 |
| `read_harness_file` | 读取当前候选中的 UTF-8 文件 |
| `query_hook_api` | 在最多 4 个唯一符号的硬预算内解析 packet 缺口 |
| `write_candidate_file` | 新建或完整替换 mutable 文件 |
| `delete_candidate_file` | 删除 mutable 文件 |
| `finalize_candidate` | 审查、校验并冻结当前 revision，或返回修复错误 |

文件路径均相对于 plugins root，并使用 POSIX 表示。写入工具接受完整文件内容，
不是文本 patch。

## 程序化 Finalizer

`finalize_candidate(summary)` 是一次原子事务：

1. 计算相对 Parent 的 changed paths；
2. 执行 Compiler 专属源码审查；
3. 执行 manifest、fixed 边界、语法、导入、装配和 Hook 契约校验；
4. 校验失败时返回紧凑、可操作的 `repair_required`；
5. 全部通过时冻结准确 revision 并返回 `candidate_ref`。

成功结果：

| 字段 | 含义 |
| --- | --- |
| `status` | 固定为 `submitted` |
| `candidate_ref` | 本次 run 内已冻结候选的引用 |
| `candidate_digest` | 候选准确文件内容的摘要 |
| `changed_paths` | 本次事务包含的文件 |
| `validation_passed` | 确定性门禁已通过 |

失败结果：

| 字段 | 含义 |
| --- | --- |
| `status` | 固定为 `repair_required` |
| `revision` | 失败候选的 workspace revision |
| `candidate_digest` | 失败候选的内容摘要 |
| `changed_paths` | 当前变更文件 |
| `errors` | 模型下一步应修复的确定性错误 |

Compiler 专属源码审查当前拒绝：

- `del config`、`del context` 等 dummy statement；
- `except Exception` 或 `except BaseException`；
- 未验证或消费 `config` 的 plugin factory；
- 读取可空的 `stage.model_input`、`stage.tool_call`、`stage.tool_result`
  后缺少对应显式类型检查。

这些检查只作用于 Compiler 新改动的 Python 文件，不改变通用 Version Store
validator 的职责。

## 输出协议

Compiler 通过 runtime 的终止工具提交 `CompilerResult`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `decision` | `submitted \| needs_revision` | 已提交候选，或机制规格仍不足 |
| `candidate_ref` | `str \| null` | `submitted` 时引用已冻结候选 |
| `implementation_summary` | `str` | 机制如何映射为 Actor Harness plugin |
| `unresolved_risk` | `str \| null` | 留给 Candidate Reviewer 的剩余风险 |

普通代码和 validation 错误必须在当前 run 内修复。`needs_revision` 只用于
`MechanismSpec` 冲突、必需能力缺失或无法在现有公开 API 内安全实现。

runtime 会解析 `candidate_ref`，拒绝模型虚构的候选。完整 diff、validation 和
changed files 由程序放入 `resource_artifacts.compiler_candidate`，无需让模型在
最终输出中重复。

## 执行流程

```text
validate CompilerInput
→ generate phase-scoped capability packet
→ render mechanism + packet into model context
→ list files and read harness.json
→ read only implementation-dependent parent files
→ write minimal component and manifest update
→ finalize_candidate
    ├─ repair_required → repair reported errors → finalize again
    └─ submitted → submit CompilerResult(candidate_ref)
→ persist Teacher transcript, usage and compiler_candidate artifact
```

## 验证边界

finalizer 证明的是确定性工程合法性，不证明：

- 自然语言机制与代码完全语义等价；
- Actor 一定按 feedback 行动；
- 机制能提升任务准确率；
- token、延迟或稳定性满足 promotion 标准。

这些问题应由语义 smoke、candidate rollout、evaluation 和 Candidate Reviewer
继续验证。
