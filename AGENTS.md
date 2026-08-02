# AGENTS.md

## 文档职责

本文档规定编码 Agent 在本仓库中开发、修改和验证代码时必须遵守的规则。

项目文档位于 `docs/`：`docs/architecture/`、`docs/reference/` 和 `docs/guides/`
是当前文档骨架；`docs/design/` 记录研究设计、决策过程和实验方案，其中历史专题可能
早于当前代码并使用旧术语；`docs/manual_v1/` 与 `docs/manual_v2/` 都是历史版本档案。
在新的编码指南正文完成前，`docs/manual_v2/python_style.md` 继续作为明确例外提供当前
Python 代码风格规范。`docs/design.md` 是早期综合设计参考。

除非任务明确要求，编码 Agent 应优先进行范围最小、可验证、可回滚的修改，避免提前实现尚未确定的架构。

## 开发环境

- 操作系统：Windows。
- 默认 Shell：PowerShell。
- 项目工作目录：`D:\_Project\Agent\search_harness`。
- Python 环境：`D:\ProgramData\miniconda3\envs\env_search_harness`。
- 执行 Python 命令时，优先直接使用该环境中的 `python.exe`，不要假设 Conda 环境已经激活。
- 所有文本文件必须使用 UTF-8 编码读写，不得依赖 Windows 系统默认编码。
- Python 读写文本时应显式指定 `encoding="utf-8"`。
- PowerShell 读写文本时应显式指定 `-Encoding utf8`。
- 禁止向系统临时目录写入任何项目内容，包括 `%TEMP%`、`%TMP%`、`$env:TEMP`、`$env:TMP` 和 `C:\Windows\Temp`。request、脚本、日志、测试夹具和中间产物必须存放在仓库内职责明确的目录；运行期临时产物优先放在对应的 `runs/components/` 或 `runs/experiments/` 目录。
- 代码中的路径处理优先使用 `pathlib.Path`，避免手工拼接路径分隔符。
- 本机工作目录和 Python 环境路径仅用于开发命令，不得硬编码进项目运行时代码。

## 文档与决策来源

- `AGENTS.md` 规定编码 Agent 的工作方式、工程约束和验证要求。
- `CONTEXT.md` 记录当前统一术语，`docs/adr/` 记录已经生效的架构决策。
- `docs/design/post-removal-normalization.md` 记录 V1 删除后的已确认架构和迁移验收。
- `docs/design/` 的其余文件记录研究架构、实验流程与历史设计。
- `docs/manual_v1/` 与 `docs/manual_v2/` 记录历史版本实现，不作为新增接口的依据；
  `docs/manual_v2/python_style.md` 的代码风格规范除外。
- 代码表示当前实现状态，但代码现状不自动等同于正确设计。

执行任务时，按以下优先级理解要求：

1. 用户在当前任务中的明确要求；
2. `AGENTS.md` 中的工程规范；
3. `CONTEXT.md` 与 `docs/adr/` 中已经确认的术语和决策；
4. `docs/design/post-removal-normalization.md` 等活动专题中的已确认设计；
5. 当前代码实现；
6. `docs/manual_v1/`、`docs/manual_v2/`、其他历史设计文档和 `design.md`。

如果文档之间存在实质冲突，不得静默选择或自行扩大任务范围；应指出冲突，并采用范围最小、可回滚的处理方式。

讨论协议定义或协议设计变更时，如果列出代码形式的数据结构，必须同时为每个字段附上一句话的简短职责描述，避免只展示类型而缺少语义边界。

`design.md` 中标记为暂定、建议或尚未写死的内容，不应被直接固化为不可替换的核心设计。重要设计决定应记录到 `docs/`，而不是只存在于代码或对话中。

## 文档修改规范

- 修改设计文档时，应优先更新对应专题文档。
- 生成供项目成员阅读的调研、审计、分析或实验报告时，正文默认使用中文；代码、协议字段、命令和必要的专业术语可保留原文。
- 不要在多个文档中重复维护同一细节；必要时通过链接引用。
- 如果发现文档冲突，应指出冲突，并修正主要归属文档。
- 未确认设计应写入 `docs/design/open-decisions.md`，不要伪装成已确认规范。
- 代码行为或接口发生变化时，应同步更新对应文档。

## 代运行结果汇报

- 当用户要求 Agent 代为运行项目、实验或角色闭环时，运行结束后必须使用有序列表给出摘要。
- 角色行为使用 `[角色]` 标记，说明该角色做了什么、发现了什么以及形成了什么结论。
- 确定性流程使用 `[机制]` 标记，说明版本提交或回滚、模型可见上下文变化、关键状态变化，以及因何转移到下一角色。
- 摘要按实际执行时间线排序，每一项只描述一个主要行为。
- 不在摘要中罗列日志写入、artifact 路径复制、内部计数器更新等不影响行为理解的维护细节。
- 推荐格式：`1. [角色] 做了什么/发现了什么/结论是什么` 或
  `1. [机制] 修改了什么，因为什么转移至什么角色`。

## 实验 Fail-fast

- 代运行期间若发现协议语义、角色职责、能力边界、Reviewer 判据或 promotion
  gate 需要改变，必须立即暂停当前实验并向用户说明，不得将语义变更作为普通
  兼容修复后继续运行。
- 不得为了让特定 Candidate 通过而放宽 MechanismSpec、prohibited behavior 或
  conformance 判据；实现与机制冲突时应保留失败证据并路由回上游角色。
- 汇报时必须区分通用工程缺陷、协议设计缺陷和案例特定补正。未经跨机制验证，
  不得把单案例跑通描述为框架能力已经可靠。

## Python 代码风格与实现规范

完整规范见 `docs/manual_v2/python_style.md`。本节只保留编码 Agent 必须优先遵守的核心约束。

- 核心框架代码优先保证稳定性、可维护性和清晰边界。
- 默认采用最小修改原则，不顺手重构，不提前实现未确认能力。
- 研究或实验脚本可以更灵活，但不得将临时代码、硬编码路径、调试逻辑或不稳定接口扩散到框架层。
- 公共接口、核心类和复杂函数应使用 type hints；函数返回值应显式标注。
- 当前阶段允许适度使用 `Any`、`dict[str, Any]` 等弱类型；数据结构稳定后再迁移为 `dataclass`、`TypedDict`、`Protocol` 或明确类型别名。
- 优先使用 `pathlib.Path`、`dataclass`、`Enum`、`Protocol`、现代类型标注等 Python 惯用写法。
- 避免 speculative abstraction / speculative implementation；只有来自明确职责或确定扩展需求的抽象才应引入。
- 默认 fail fast；禁止裸 `except`；捕获异常时应捕获明确异常类型并保留上下文。
- 核心代码禁止硬编码关键路径、设备名、seed、重要超参数和 magic number。
- 框架代码使用 `logging`；实验脚本和一次性脚本可以使用 `print`。
- 涉及核心逻辑、接口变更、较大更新或潜在风险的改动时，应补充最小测试或 smoke test。
- 小改动不必每次都运行完整验证；但最终回复中应说明是否进行了验证，或说明未验证的原因。
- 尽量不留下 TODO 或 placeholder；如果必须留下，应写明原因和后续预期。
- 评估 Teacher 角色或提示词稳定性时，默认对同一输入并行执行 3 次；结果分歧明显时可扩展到 5 次，不得仅凭单次调用声称模型行为稳定。
