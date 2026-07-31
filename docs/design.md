# 面向小模型 Search Agent 的自进化 Harness 设计参考报告

## 0. 摘要

本项目旨在研究并实现一种面向小基础模型的 agent harness 自动适配机制。其核心问题是：在固定小模型、固定领域任务、固定工具环境和不可变 agent core loop 的前提下，是否可以利用外部强模型在离线阶段观察、干预、回滚重生成、归因和提交结构化 patch，逐步构造出一套适配该小模型的可部署 harness，使最终系统在不依赖外部强模型在线参与的情况下获得更好的 search agent 能力。

项目的基本判断是：真实业务场景中，由于成本、延迟和部署约束，小模型会被大量使用；但小模型通常不具备强模型那种自由规划、工具选择、异常恢复、证据整合和自我验证能力。因此，小模型并不适合简单套用“高自由度 agent loop”。相比之下，小模型更可能受益于模型外部的结构化支持，包括 prompt、工具、parser、validator、memory、workflow extension、controller policy、retry policy、schema repair、review gate 等。

本项目不是直接训练小模型，也不是让外部强模型在线替小模型完成任务，而是探索一种“软干预到硬化”的 harness 进化路径：外部强模型先在离线适配阶段通过 hook 给出局部、非题目相关的指导或审阅，并通过 prefix-fork / trajectory-fork 验证不同指导是否有效；随后将稳定有效的干预模式编译为 registry extension，形成最终由小模型独立使用的 harness。

------

## 1. 项目目标

### 1.1 核心目标

构建一个实验系统，用于验证以下问题：

给定一个固定小模型 actor、一个 controlled-corpus multi-hop QA 任务环境、一个基础自由 agent loop、一个可扩展 registry 机制，以及一个外部强模型 adapter，是否可以自动进化出一套适配该小模型的 harness，使最终小模型在不依赖外部强模型的情况下取得更好的 search agent 表现？

### 1.2 研究假设

本项目基于以下假设：

1. **小模型需要更强的外部结构支持。**
   小模型在开放 agent loop 下可能存在工具调用不稳定、schema 错误、过早回答、搜索不足、证据整合失败、无法自我纠错等问题。适当的 harness 可以缓解这些问题。
2. **不同小模型可能需要不同 harness。**
   不同基础模型在指令跟随、格式遵循、长上下文利用、工具调用、反思能力、停止判断等方面存在差异，因此适配它们的 harness 也可能不同。
3. **强模型的价值不应体现在在线代做任务，而应体现在离线发现结构。**
   外部强模型用于观察失败、提出局部指导、探索有效干预、编译 harness patch。最终部署时，外部强模型应完全退出。
4. **软干预可以逐渐硬化为稳定组件。**
   如果某类局部指导在多个 prefix、多个样本、多个采样下稳定有效，那么它可能对应一个可固化的 prompt、tool、validator、parser、controller policy 或 workflow extension。
5. **自由 loop 可以通过 registry extension 演化出结构化流程。**
   初始 actor loop 不预设复杂 workflow，而是允许外部适配过程逐渐发现小模型需要哪些约束和引导。

------

## 2. 非目标与边界

### 2.1 非目标

本项目第一阶段不以以下内容为主要目标：

1. 训练或微调 actor 模型。
2. 构建开放 web search deep research agent。
3. 追求通用 agent 框架能力。
4. 让外部强模型在线参与最终推理。
5. 让外部强模型直接修改 agent core loop。
6. 让外部强模型直接提供题目相关 query、实体、答案线索或证据缺口。
7. 一开始就证明跨多个小模型的普遍结论。

### 2.2 第一阶段任务范围

第一阶段建议使用：

- controlled corpus；
- multi-hop QA；
- 固定 search / open / read 类基础工具；
- 固定 actor 小模型；
- 不含外部副作用的工具调用；
- 可重复运行的评估环境；
- 可缓存的检索结果与工具输出。

不建议第一阶段直接使用开放网页搜索，因为网页结果会变化，工具观测不稳定，prefix-fork 的可比性较差，难以判断收益来自 harness 还是搜索结果波动。

------

## 3. 系统总览

系统分为两层 harness：

1. **Actor Harness**
   服务于小模型 actor，用于增强其完成 search agent 任务的能力。
2. **Adapter Harness**
   服务于外部适配强模型，用于管理角色、上下文、工具、memory、patch、审计、评估与轨迹访问。

整体结构如下：

```text
Experience / Eval Data
        |
        v
+----------------------+
|   Experiment Runner  |
+----------------------+
        |
        v
+----------------------+
|   Actor Core Loop    |  <-- 不可直接修改
+----------------------+
        |
        v
+----------------------+
| Registry Extensions  |  <-- 可新增/修改
| prompts/tools/memory |
| validators/policies  |
+----------------------+
        |
        v
Actor Rollouts / Traces
        |
        v
+----------------------+
| External Adapter     |
| Critic/Intervention/ |
| Compiler roles       |
+----------------------+
        |
        v
Patch Proposal / Patch Submit / Eval / Audit
```

最终导出的部署系统应为：

```text
Small Actor Model + Actor Core Loop + Learned Registry Extensions
```

其中不包含外部强模型在线参与。

------

## 4. 核心不变量

以下是不应被外部适配 agent 修改的系统不变量：

1. agent core loop 不可被直接修改；
2. state manager 核心逻辑不可被直接修改；
3. prefix-fork runner 核心逻辑不可被直接修改；
4. evaluator 不可被修改；
5. 数据划分不可被修改；
6. golden answer 不可被修改；
7. audit 模块不可被绕过；
8. registry loader 核心逻辑不可被修改；
9. 最终 actor harness 不允许调用外部强模型；
10. adapter memory 不允许保存题目级信息。

外部适配 agent 只能通过指定工具和指定 schema，在可变扩展层新增或修改组件。

------

## 5. 数据划分与可见性策略

当前数据划分按用途和可见性分为三类。

### 5.1 Experience Set / 开发经验集

用途：

- 收集 actor-only 轨迹；
- 分析失败模式；
- 进行 label-visible 诊断；
- 探索 soft intervention；
- 形成 harness patch 候选。

可见性：

- 外部模型可见输入样本；
- 外部模型可见 golden answer；
- 外部模型可见完整 actor trajectory；
- 外部模型可做深度失败分析。

注意：

Experience Set 中看到的题目级信息不能进入 adapter 长期 memory，也不能通过角色切换传递给 Compiler 或 Intervention。只能抽象成 failure pattern、schema pattern、harness gap、通用改进方向等非题目级信息。

### 5.2 Visible-ID Eval Set / 可见同分布评估集

用途：

- 每次 patch 提交后进行同分布验证；
- 检查 patch 是否在非 label-visible 样本上有效；
- 提供有限反馈，避免过度泄漏。

可见性：

- 外部模型可见输入问题；
- 外部模型可见 actor 轨迹；
- 外部模型可见是否正确，0/1；
- 外部模型不可见 golden answer；
- 外部模型不可见错误类型。

这部分用于观察 patch 的同分布泛化能力，但不向外部模型泄漏答案或结构化错误标签。

### 5.3 Blind-OOD Eval Set / 盲测域外评估集

用途：

- 检查 harness 是否在训练分布外泛化；
- 作为更严格的 patch 选择信号；
- 观察是否出现对 Experience Set 的过拟合。

可见性：

- 外部模型不可见样本；
- 外部模型不可见 actor 轨迹；
- 外部模型不可见 golden answer；
- 只返回 aggregate score。

### 5.4 Final Holdout / 最终盲测集

Final Holdout 原则上应该存在，但第一阶段暂不作为阻塞项。

如果后续目标是形成更严谨的实验报告或论文式结果，建议增加一个最终只运行一次的完全盲测集。它不参与任何 patch selection，只用于最终评估。

------

## 6. Actor Core Loop

### 6.1 初始 loop 形态

第一阶段基础 loop 保持自由，不预设强流程化结构。

核心原因：

项目希望观察外部适配过程是否会自然发现“小模型不适合过高自由度”，而不是一开始就把强流程先验写死。

初始 actor loop 可以类似自由 ReAct-style loop：

```text
observe task
construct prompt
model generates thought/action/final answer
parse output
if action:
    call tool
    append observation
    continue
if final:
    submit answer
```

### 6.2 Hook 设计

虽然 core loop 保持自由，但需要暴露足够 hook 供 registry extension 接入。

建议初始 hook 包括：

1. `pre_prompt`
   在构造 actor prompt 前触发。
2. `post_prompt`
   在 prompt 构造后、模型调用前触发。
3. `post_model`
   在 actor 生成后、解析前触发。
4. `pre_parse`
   在解析 action / answer 前触发。
5. `post_parse`
   在解析后触发。
6. `pre_tool`
   在工具调用前触发。
7. `post_tool`
   在工具返回后触发。
8. `pre_final`
   在提交最终答案前触发。
9. `post_final`
   在最终答案提交后触发。
10. `on_error`
    在 parser、tool、validator 或 runtime 出错时触发。

这些 hook 不等于固定 workflow，只是为未来 extension 提供插槽。

### 6.3 Core loop 与 extension 的关系

core loop 只负责：

- 维护基本运行过程；
- 调用 registry 中已启用 extension；
- 记录 trace；
- 维护 state；
- 执行工具调用；
- 执行终止条件；
- 与 evaluator 对接。

core loop 不应包含大量手写任务逻辑。任务逻辑、控制策略、验证策略、schema 修复、review gate 等应尽可能通过 registry extension 加入。

------

## 7. Registry Extension 机制

### 7.1 设计目标

registry 是 actor harness 的统一扩展层。外部适配 agent 不能直接修改 core loop，只能通过 registry 新增或修改组件。

registry 需要支持以下目标：

1. 可加载；
2. 可审计；
3. 可回滚；
4. 可版本化；
5. 可按 hook 接入；
6. 可控制访问状态；
7. 可统计贡献；
8. 可在 patch 中独立评估。

### 7.2 可注册组件类型

当前不强行限制组件具体实现形式，但建议 registry 至少支持以下类别：

1. prompt component；
2. skill document；
3. tool；
4. parser；
5. validator；
6. schema repairer；
7. memory module；
8. workflow extension；
9. controller policy；
10. retry policy；
11. budget policy；
12. review policy；
13. tool routing policy；
14. state variable；
15. failure taxonomy entry。

组件内部可以是：

- prompt；
- 模板；
- Python 代码；
- 配置；
- 状态机；
- 小模型调用；
- 确定性规则；
- 组合式 wrapper。

不应在第一版过度限制组件实现方式，但所有组件必须通过 registry 暴露给 actor loop。

### 7.3 Registry 组件模板

为了让外部模型能稳定提交 extension，需要提供一个宽松模板。模板不应把实现方式限制死，但应要求声明基本信息。

示例：

```yaml
extension_id: string
extension_type: prompt_component | tool | parser | validator | memory | controller_policy | workflow_extension | other
name: string
version: string
description: string

mount:
  hooks:
    - pre_prompt
    - post_model
    - pre_tool
  priority: int
  enabled: true

interface:
  input_schema: optional
  output_schema: optional
  exposed_variables:
    read:
      - actor_state
      - current_trace
    write:
      - scratchpad
      - memory_state

implementation:
  kind: prompt | code | config | state_machine | model_call | composite | other
  content: string_or_file_reference

constraints:
  may_call_actor_model: true_or_false
  may_call_external_adapter_model: false
  may_access_gold_answer: false
  may_modify_core_loop: false
  may_modify_evaluator: false

audit:
  declared_intent: string
  possible_risks: string
  expected_failure_modes_addressed:
    - string
```

这是建议模板，不是最终强约束。实际实现可以根据工程复杂度调整。

------

## 8. Actor State Manager 与 Prefix-Fork

### 8.1 State Manager 职责

State Manager 是 actor 运行时的关键模块，用于保证轨迹可复现、可 fork、可比较。

它至少需要管理：

1. 当前 prompt 组成；
2. system / developer / task prompt；
3. actor conversation history；
4. scratchpad；
5. working memory；
6. 长期 memory 状态；
7. tool state；
8. tool call history；
9. 检索缓存；
10. 当前预算；
11. 当前 retry 计数；
12. parser 状态；
13. validator 状态；
14. workflow extension 状态；
15. registry 已加载组件；
16. sampling config；
17. random seed；
18. hook execution log；
19. external intervention log。

### 8.2 Prefix-Fork 的定义

本项目中的“回滚”更准确地称为 prefix-fork 或 trajectory-fork。

它不是生产事务回滚，而是：

> 从某个 actor prefix / runtime state snapshot 出发，重新生成后续轨迹，用于离线比较不同指导或不同采样的效果。

对 actor 来说，这是从历史状态继续运行；对外部适配 agent 来说，这是一个显式可调用工具。

### 8.3 Prefix-Fork 的用途

prefix-fork 只用于离线优化，不作为最终部署默认机制。

主要用途：

1. 比较不同 soft guidance；
2. 评估同一 guidance 下 actor 采样稳定性；
3. 观察某类干预是否改变失败路径；
4. 验证某个 harness extension 是否改善局部行为；
5. 分析 failure transition；
6. 为 hardening 提供证据。

### 8.4 两类 pass@k

本项目需要同时支持两类 pass@k。

#### pass@k over guidance

同一个 prefix 下，外部适配 agent 提供 k 种不同局部 guidance，让 actor 分别继续运行。

目标是探索：

- 哪种指导更有效；
- 哪种指导更容易被小模型遵循；
- 哪种指导更适合硬化为 harness。

#### pass@k over actor sampling

固定同一个 guidance，让 actor 采样 k 次。

目标是评估：

- 指导是否稳定；
- 成功是否依赖偶然采样；
- actor 在该 guidance 下是否仍然高方差；
- 是否需要更强的 harness 约束。

可以组合成：

```text
K_guidance × K_actor_sampling
```

例如每个 prefix 生成 3 种 guidance，每种 guidance 采样 3 条 actor 轨迹，总计 9 条 forked rollout。

### 8.5 工具状态与副作用

第一阶段建议仅使用无外部副作用工具，例如 search、open、read、extract、review、analysis、verify、memory read/write 等。

如果存在工具状态，必须由 State Manager 管理并可快照化。否则不同 fork 之间不可比较。

------

## 9. 外部适配 Agent 设计

### 9.1 统一 Agent，多角色状态

外部适配器暂定为一个统一 agent，而不是多个独立 agent。它通过显式角色状态切换不同 prompt 和工具集。

角色包括：

1. Critic；
2. Intervention；
3. Compiler。

不同角色拥有不同上下文、工具、权限和可见信息。

所有记录和持久化内容都必须标注：

- 当前轮次；
- 当前角色；
- 当前 harness 版本；
- 当前数据划分；
- 当前客观状态；
- 当前 patch 状态；
- 当前可见性边界。

### 9.2 通用工具集

外部适配 agent 始终可用的通用工具包括：

1. 获取当前角色信息；
2. 切换当前角色；
3. 读取当前 harness 配置；
4. 读取 registry；
5. 读取更新日志；
6. 读取 patch log；
7. 维护 adapter memory；
8. 查看实验轮次；
9. 查看评估状态；
10. 查看可用工具列表。

这些工具构成 Adapter Harness 的基础控制面。

------

## 10. Critic 角色

### 10.1 职责

Critic 用于观察纯 actor rollout 和当前 harness，分析失败模式、筛选轨迹、发现可改进方向。

它主要处理：

- actor-only 完整轨迹；
- 当前 harness 配置；
- registry 当前状态；
- 历史 patch；
- changelog；
- evaluation summary。

### 10.2 权限

Critic 可以：

1. 读取 Experience Set 上的完整 actor trajectory；
2. 在 Experience Set 上读取 golden answer；
3. 编写脚本筛选轨迹；
4. 统计失败模式；
5. 发现高频 schema 问题；
6. 分析当前 harness gap；
7. 形成抽象改进意见；
8. 通过 role handoff packet 传递非题目级信息。

Critic 不应：

1. 将具体题目文本写入长期 memory；
2. 将 golden answer 写入长期 memory；
3. 将具体文档内容、实体、答案路径传给 Intervention 或 Compiler；
4. 直接修改 harness；
5. 直接提交 patch。

### 10.3 输出结构

Critic 暂不强制固定输出 schema。早期实验应允许 Critic 自由分析，以便观察外部模型自然发现哪些问题。

但日志层可以鼓励 Critic 记录以下信息：

- failure pattern；
- 涉及的大致样本数量；
- 关联的 actor 行为缺陷；
- 可能的 harness gap；
- 可能的 intervention 方向；
- 可能的 hardening target；
- 风险或不确定性。

这些字段是推荐格式，不是硬约束。

------

## 11. Intervention 角色

### 11.1 职责

Intervention 是离线适配阶段的参与者。它会在 actor loop 的 hook 处被激活，对当前 actor 行为进行非题目相关的局部审阅或指导。

它的目标不是替 actor 做题，而是探索：

- 哪类高层级指导能让小模型表现更好；
- 哪类常见错误可以自动修复；
- 哪类局部约束值得硬化；
- 哪些 prefix 适合进行 fork 比较。

### 11.2 允许行为

Intervention 可以：

1. 查看当前 hook 上下文；
2. 查看当前 actor state 摘要；
3. 调用 actor 已有工具；
4. 调用 prefix-fork 工具；
5. 做 pass@k over guidance；
6. 做 pass@k over actor sampling；
7. 提交局部指导；
8. 提交评审决定；
9. 对工具参数进行审阅但不修改语义内容；
10. 对非内容型 schema 问题进行自动补正；
11. 提出 harness modification proposal。

### 11.3 禁止行为

Intervention 在提交给 actor 的指导或评审中，不允许包含题目相关内容。

禁止包括：

1. 具体 search query；
2. 具体候选答案；
3. 具体桥接实体；
4. 具体文档 ID；
5. 具体证据缺口；
6. “应该打开第几个结果”这类题目相关动作；
7. 能让 actor 直接靠外部强模型提示完成任务的信息。

### 11.4 允许的 soft guidance 类型

允许给 actor 的指导包括：

1. 当前证据不足，不建议直接回答；
2. 请检查工具调用参数是否符合 schema；
3. 请避免把未验证内容写入最终答案；
4. 请在回答前确认多个证据是否一致；
5. 请压缩下一步搜索目标；
6. 当前存在 premature answer 风险；
7. 当前输出格式可能无法被 parser 解析；
8. 当前工具调用缺少非语义必填字段；
9. 当前需要继续使用可用工具验证；
10. 当前应避免重复搜索相同内容。

这些指导是行为层、格式层、过程层的，而不是题目内容层的。

### 11.5 Schema Repair

Intervention 可以对简单、常见、非内容型 schema 问题做自动修复，以推进推理进程。

例如：

- JSON 外层括号缺失；
- 字段名轻微错误；
- 字段类型可安全转换；
- 多余自然语言包裹合法 JSON；
- 缺少非语义默认字段；
- action 格式稳定但不完全匹配 schema；
- 工具名大小写或别名错误。

但 Intervention 不能补全题目相关参数。例如不能替 actor 填写具体 query、实体、文档 ID 或答案内容。

如果 schema 问题高频出现，则应记录为 patch 候选：

- parser auto-repair；
- schema normalizer；
- tool-call validator；
- retry policy；
- prompt instruction；
- tool-call few-shot example；
- pre-tool self-check；
- default field filler。

原则是：

> Intervention 可以推进非内容型执行障碍，但不能替 actor 完成题目内容决策。高频 schema 修复应沉淀为可硬化的 harness 改进信号。

------

## 12. Compiler 角色

### 12.1 职责

Compiler 负责将有效的 soft intervention、failure pattern、schema repair、prefix-fork 结果和 critic 意见转化为结构化 harness patch。

它不是简单总结者，而是将“软经验”硬化为 registry extension 的角色。

### 12.2 权限

Compiler 可以：

1. 读取抽象 failure pattern；
2. 读取 intervention 统计；
3. 读取 prefix-fork 对比结果；
4. 读取 pass@k 结果；
5. 读取 patch history；
6. 新增或修改 registry extension；
7. 提交 patch；
8. 触发评估；
9. 根据需要继续提交多个 patch；
10. 根据需要切换回 Critic 或 Intervention。

Compiler 不应：

1. 读取 Experience Set 中具体题目级信息；
2. 读取 golden answer；
3. 修改 evaluator；
4. 修改 core loop；
5. 修改数据划分；
6. 将题目级信息写入 harness；
7. 让最终 harness 调用外部强模型。

### 12.3 Intervention 与 Compiler 的边界

Intervention 可以提出 harness modification proposal，但正式 patch submit 由 Compiler 完成。

这样可以保持：

- Intervention 聚焦在线局部行为；
- Compiler 聚焦结构化硬化；
- patch log 更清晰；
- 角色权限更可审计。

------

## 13. Role Handoff 与 Memory Policy

### 13.1 问题背景

Experience Set 是 label-visible 的，Critic 可能看到具体问题、答案和完整轨迹。如果这些题目级信息进入长期 memory 或传递给 Compiler，就会污染 harness，使系统可能过拟合或泄漏答案。

因此，需要严格区分：

- case-level 信息；
- general pattern 信息。

### 13.2 Adapter Memory 规则

外部适配 agent 的长期 memory 不允许保存题目级信息。

不允许保存：

1. 具体问题文本；
2. golden answer；
3. 具体实体；
4. 具体文档 ID；
5. 具体检索结果内容；
6. 能反推出答案的轨迹摘要；
7. 样本级 shortcut；
8. 数据集中特定样本模式。

允许保存：

1. 抽象 failure pattern；
2. 高频 schema 问题；
3. 工具调用格式缺陷；
4. 小模型行为倾向；
5. 非题目相关的 prompt 缺陷；
6. 通用 harness gap；
7. patch 效果趋势；
8. registry 组件经验；
9. 评估指标变化；
10. 审计发现。

### 13.3 Role Handoff Packet

角色切换时，不允许直接携带完整上下文。应通过 handoff packet 传递抽象信息。

建议模板：

```yaml
handoff_id: string
from_role: critic | intervention | compiler
to_role: critic | intervention | compiler
round_id: string
harness_version: string

allowed_summary:
  - string

failure_patterns:
  - pattern_id: string
    description: string
    frequency_estimate: optional
    severity: optional

proposed_intervention_patterns:
  - string

proposed_patch_directions:
  - string

forbidden_case_references_removed: true

audit_notes:
  - string
```

handoff packet 应经过自动审计，检查是否包含题目级信息。

------

## 14. Soft-to-Hard Hardening 标准

一个 soft intervention 或 failure pattern 不应因为单次有效就被硬化。建议满足以下条件后再进入 patch 候选：

1. 重复出现；
2. 在多个样本或多个 prefix 上出现；
3. pass@k over guidance 显示该指导有效；
4. pass@k over actor sampling 显示效果稳定；
5. 能抽象成通用 harness 组件；
6. 不依赖具体题目内容；
7. 在 Visible-ID Eval Set 上不退化；
8. 在 Blind-OOD Eval Set 上不明显退化；
9. audit 未发现泄漏或 shortcut；
10. patch 影响范围可解释、可回滚。

可以概括为：

```text
重复出现 + pass@k 有效 + validation 通过 + regression 不退化
```

------

## 15. Patch Protocol

### 15.1 Patch 粒度

patch 应小步提交，但允许连续提交。

每个 patch 尽量对应一个明确假设，例如：

- 加一个 schema normalizer；
- 加一个 before-final-answer verifier；
- 修改某个 prompt component；
- 新增一个 duplicate-query detector；
- 新增一个 search budget controller；
- 新增一个 evidence consistency checker。

如果一个改进方向包含多个相关改动，可以连续提交多个 patch，逐步验证。

### 15.2 Patch 结构

建议 patch 包含：

```yaml
patch_id: string
parent_harness_version: string
proposed_by_role: compiler
patch_type: prompt | tool | parser | validator | memory | controller | workflow_extension | other

motivation:
  observed_failure_patterns:
    - string
  expected_improvement: string
  non_goal: string

changes:
  registry_extensions_added:
    - string
  registry_extensions_modified:
    - string
  registry_extensions_removed:
    - string

risk:
  possible_overfit: string
  possible_cost_increase: string
  possible_behavioral_regression: string

constraints:
  modifies_core_loop: false
  modifies_evaluator: false
  accesses_gold_answer: false
  calls_external_adapter_model_at_runtime: false

evaluation:
  status: pending
  experience_score: null
  visible_id_eval_score: null
  blind_ood_eval_score: null
  cost_metrics: null
  regression_result: null
```

Patch 提交时不包含 `audit` 字段。评估结果和审计结果不由外部模型自己填写，应由系统模块在 patch 提交后填充；审计结果只允许为 `passed` 或 `rejected`。

### 15.3 Changelog

每次 patch 后应写入 changelog：

- harness version；
- patch id；
- patch 摘要；
- 修改组件；
- 触发原因；
- 评估结果；
- 是否合入；
- 是否回滚；
- 后续观察。

changelog 是外部适配 agent 重要的长期可见信息，但不应包含题目级内容。

------

## 16. Audit 机制

### 16.1 审计目标

audit 负责防止：

1. 答案泄漏；
2. 数据集 shortcut；
3. 修改 evaluator；
4. 修改数据划分；
5. 修改 golden answer；
6. 绕过工具调用；
7. 让最终 harness 调外部强模型；
8. 将题目级信息写入 memory；
9. 将题目级信息写入 prompt、skill、tool 或 policy；
10. 通过样本 ID、hash、顺序等方式过拟合。

### 16.2 静态审计

静态审计检查：

- patch diff；
- registry extension；
- prompt；
- tool code；
- memory；
- handoff packet；
- changelog；
- config。

检查项包括：

- 是否出现 golden answer 字符串；
- 是否出现样本 ID；
- 是否出现具体题目文本；
- 是否出现具体文档 ID；
- 是否修改 evaluator；
- 是否修改 split；
- 是否访问 forbidden variables；
- 是否新增外部强模型 runtime call；
- 是否出现 hash-based branching；
- 是否包含硬编码答案映射。

### 16.3 模型审计

模型审计用于发现规则审计难以覆盖的问题，例如：

- patch 是否像是在利用数据集分布 shortcut；
- prompt 是否过度贴合 Experience Set；
- tool 是否暗含具体题目路径；
- memory 是否包含可反推答案的信息；
- workflow 是否异常依赖某类样本模式；
- handoff packet 是否含有过细 case-level 信息。

模型审计可以由外部强模型承担，但其输出只作为 audit note，不直接决定最终分数。

### 16.4 审计结果

第一版 Audit 使用二态结果：

- `passed`：未发现阻塞性治理违规，Patch 可以进入 Controlled Evaluation。
- `rejected`：发现阻塞性治理违规，或存在无法自动消解的数据泄漏、越权修改、评估篡改、题目级信息写入等风险，Patch 不得进入当前 Harness。

系统不设置 `pending` 或 `warning` 作为正式 Audit 状态。由于第一版流程按同步方式执行，`pending` 只作为内部执行过程，不进入 Patch 协议。由于理想运行期间不依赖人类介入，所有潜在风险必须由自动规则归约为 `passed` 或 `rejected`。

Audit 可以记录 `audit_notes` 和 `risk_flags`，但这些字段只用于解释和后续分析，不形成第三种状态。

------

## 17. Evaluation Protocol

### 17.1 每次 patch 后的评估

每次 patch 提交后，系统应自动执行：

1. audit；
2. Experience Set 回放或抽样评估；
3. Visible-ID Eval Set 评估；
4. Blind-OOD Eval Set 评估；
5. regression 检查；
6. cost 统计；
7. trace 统计；
8. patch result 填充。

### 17.2 评估反馈可见性

对外部适配 agent 的反馈应受数据集可见性控制。

Experience Set：

- 可见样本；
- 可见答案；
- 可见轨迹；
- 可做深度分析。

Visible-ID Eval Set：

- 可见输入问题；
- 可见 actor 轨迹；
- 可见 0/1 正误；
- 不可见答案；
- 不可见错误类型。

Blind-OOD Eval Set：

- 不可见样本；
- 不可见轨迹；
- 不可见答案；
- 只返回 aggregate score。

### 17.3 Regression

regression 不只看总体分数，也应关注：

- 已成功样本是否变失败；
- schema 错误是否上升；
- tool call 是否失控；
- token cost 是否大幅上升；
- premature answer 是否增加；
- 搜索次数是否异常增加；
- final answer 格式是否退化。

------

## 18. 指标体系

### 18.1 主指标

第一阶段以正确率为主。

可使用：

- Exact Match；
- F1；
- answer accuracy；
- evidence-supported accuracy。

具体取决于 multi-hop QA 数据集和 evaluator。

### 18.2 成本指标

成本初期权重较小，在正确率进入平台期后再重点优化。

成本指标包括：

- token count；
- model calls；
- tool calls；
- search calls；
- latency；
- average rollout length；
- cost per successful answer。

### 18.3 稳定性指标

包括：

- pass@k over guidance；
- pass@k over actor sampling；
- invalid action rate；
- parser failure rate；
- schema repair rate；
- retry rate；
- final answer format validity。

### 18.4 Harness 进化指标

这是本项目最重要的过程性指标。

建议重点报告：

1. **Intervention Rate Decay**
   外部模型每条轨迹或每个 step 平均干预次数是否下降。
2. **Soft-Hard Gap Closing**
   hard harness 是否逐渐接近 soft-advised upper bound。
3. **Patch Acceptance Rate**
   提出的 patch 有多少通过 audit 和 eval。
4. **Patch Effect Size**
   每类 patch 对正确率、成本、稳定性的影响。
5. **Failure Type Shift**
   失败类型是否从低级 schema/tool 错误转向更高层语义错误。
6. **Registry Growth Curve**
   harness 扩展数量和性能提升之间的关系。

### 18.5 推荐曲线

建议画三条核心曲线：

1. actor-only with current hard harness；
2. actor + soft intervention；
3. final hard harness without external adapter。

理想现象是：

- hard harness 分数逐渐上升；
- soft intervention 额外收益逐渐下降；
- intervention rate 下降；
- soft-hard gap 缩小。

这能直接体现“软适配逐渐硬化”的过程。

------

## 19. Failure Taxonomy

系统应维护可扩展 failure taxonomy。

初始类别可以包括：

1. query formulation failure；
2. insufficient search；
3. over-search；
4. duplicate search；
5. wrong document selection；
6. evidence extraction failure；
7. missing bridge entity；
8. contradiction unresolved；
9. premature final answer；
10. hallucinated evidence；
11. invalid tool call；
12. parser failure；
13. schema violation；
14. memory pollution；
15. verifier failure；
16. budget exhaustion；
17. answer synthesis error；
18. citation mismatch；
19. unable to recover from empty result；
20. context overflow。

Critic 可以新增类别，但新增类别应进入 taxonomy registry，并经过审计和版本化。

------

## 20. Workflow Extension 与 Controller Policy

### 20.1 设计原则

基础 loop 保持自由，但允许通过 registry 新增 workflow extension 或 controller policy。

这意味着系统不是一开始写死流程，而是允许适配过程逐渐发现并固化结构。

### 20.2 可新增 extension 示例

外部适配 agent 可以新增：

1. before-final-answer review gate；
2. evidence sufficiency checker；
3. answer verification gate；
4. search budget controller；
5. duplicate-query detector；
6. retry-on-invalid-schema policy；
7. tool-call normalizer；
8. memory write gate；
9. citation consistency checker；
10. premature-answer blocker；
11. post-search summarizer；
12. query refinement helper；
13. evidence table manager。

### 20.3 模板

建议 workflow extension 使用宽松模板：

```yaml
extension_type: workflow_extension
name: string
description: string
trigger_hooks:
  - pre_final
  - post_tool

activation_condition:
  type: natural_language_or_code_condition
  content: string

behavior:
  type: block | warn | modify_prompt | call_tool | update_state | request_retry | other
  content: string

state_access:
  read:
    - current_trace
    - tool_history
    - scratchpad
  write:
    - scratchpad
    - controller_state

constraints:
  no_task_specific_content: true
  no_external_adapter_runtime_call: true
  no_core_loop_modification: true

expected_effect:
  target_failure_types:
    - premature final answer
    - schema violation
  cost_impact: low | medium | high
```

模板用于引导，不用于限制所有可能实现。

------

## 21. 第一阶段 MVP 路线

### Phase 0：最小实验环境

目标：

- 固定 controlled corpus；
- 固定 multi-hop QA 数据；
- 固定基础 search/open/read 工具；
- 固定小模型 actor；
- 简单自由 actor loop；
- 基础 evaluator；
- trace logger。

产出：

- actor-only baseline；
- 基础轨迹格式；
- 初始失败样本。

### Phase 1：Registry 与 State Manager

目标：

- 实现 registry loader；
- 实现 extension 挂载；
- 实现 state snapshot；
- 实现 prefix-fork；
- 实现 trace diff；
- 实现工具结果缓存。

产出：

- 可从任意 prefix fork rollout；
- 可比较多个 guidance；
- 可复现 actor trajectory。

### Phase 2：Adapter Harness

目标：

- 实现外部适配 agent；
- 实现角色状态；
- 实现角色工具集；
- 实现 role-specific prompt；
- 实现 handoff packet；
- 实现 adapter memory policy。

产出：

- Critic 可读 Experience Set 轨迹；
- Intervention 可在 hook 处参与；
- Compiler 可提交 patch。

### Phase 3：Soft Intervention

目标：

- 在 hook 处启用 Intervention；
- 允许非题目相关局部指导；
- 支持 schema repair；
- 支持 prefix-fork pass@k；
- 记录 intervention log。

产出：

- soft-advised upper bound；
- guidance effectiveness 统计；
- schema 问题统计；
- soft intervention candidate pool。

### Phase 4：Patch 与评估闭环

目标：

- 实现 patch protocol；
- 实现 audit；
- 实现 eval trigger；
- 实现 changelog；
- 实现 patch result 自动填充；
- 支持小步提交和回滚。

产出：

- soft-to-hard 闭环；
- patch 版本演化；
- hard harness 性能曲线。

### Phase 5：核心实验

目标：

- 比较 actor-only baseline；
- 比较 soft-advised；
- 比较 hard harness；
- 比较不同 patch 类型；
- 观察 intervention rate decay；
- 观察 soft-hard gap closing。

产出：

- 项目核心实验结果；
- harness 进化分析；
- failure taxonomy shift；
- patch effectiveness report。

------

## 22. 关键风险与缓解

### 22.1 外部强模型泄漏答案

风险：

Experience Set label-visible，外部模型可能把题目级信息写入 harness。

缓解：

- adapter memory 禁止题目级信息；
- role handoff packet 审计；
- patch 静态审计；
- model audit；
- eval set 不暴露答案；
- Blind-OOD aggregate-only 评估。

### 22.2 系统退化为强模型在线代做

风险：

Intervention 若给具体 query、答案线索或证据缺口，就会变成强模型带小模型做题。

缓解：

- soft guidance 禁止题目相关内容；
- 具体内容建议必须 actor-side 工具化；
- 最终 harness 禁止调用外部强模型；
- 报告 hard harness without adapter 作为主结果。

### 22.3 Harness 搜索空间过大

风险：

外部模型自由度过高，patch 难以归因、难以复现。

缓解：

- core loop 不可变；
- registry 统一挂载；
- patch 结构化；
- 小步提交；
- changelog；
- audit；
- regression。

### 22.4 过早限制搜索空间

风险：

如果只允许改 prompt 或固定几类工具，可能引入过强先验，限制发现真正有效的 harness。

缓解：

- 开放提议；
- 结构化提交；
- registry 支持多种 extension；
- 工具实现方式不写死；
- 实验中观察哪些 extension 自然有效。

### 22.5 Adapter 自身上下文混乱

风险：

外部适配 agent 长期运行、多角色切换、多 patch 提交，容易遗忘、混淆或泄漏。

缓解：

- adapter harness；
- role-specific prompt；
- role-specific tool loading；
- handoff packet；
- changelog；
- memory policy；
- 客观状态标注；
- 角色切换记录。

### 22.6 Prefix-fork 不可比

风险：

如果 state snapshot 不完整，不同 fork 的结果不可比较。

缓解：

- State Manager 统一管理 prompt、轨迹、memory、tool state、budget、seed、registry；
- tool output cache；
- 无副作用工具优先；
- fork metadata 完整记录。

------

## 23. 后续可扩展实验

第一阶段单模型跑通后，可以扩展以下实验。

### 23.1 多模型适配实验

选择多个小模型 actor，分别进化 harness，然后做交叉评估：

```text
Harness evolved for Model A -> Model A / B / C
Harness evolved for Model B -> Model A / B / C
Generic harness -> Model A / B / C
```

目标是验证：

- harness 是否具有 model-specific 特征；
- 某模型适配出的 harness 是否迁移到其他模型；
- 不同模型需要的约束类型是否不同。

### 23.2 先验强度实验

比较不同初始 loop：

1. free loop；
2. partially structured loop；
3. strongly structured loop。

观察：

- 自进化速度；
- 最终性能；
- patch 数量；
- intervention rate decay；
- 是否强先验降低搜索成本；
- 是否强先验限制最终上限。

### 23.3 成本优化阶段

当正确率进入平台期后，引入成本约束：

- 降低搜索次数；
- 减少 token；
- 减少 retry；
- 减少无效工具调用；
- 优化 cost-per-success。

### 23.4 Final Holdout

在主要系统稳定后，增加最终盲测集：

- 不参与 patch selection；
- 不暴露样本；
- 不暴露轨迹；
- 只最终运行一次；
- 用于报告最终泛化性能。

------

## 24. 当前暂定但未写死的决策

以下内容当前暂定，但不应在实现中写死：

1. 是否立即加入 Final Holdout；
2. Critic 是否需要固定输出 schema；
3. Compiler 每次提交一个 patch 还是多个连续 patch；
4. registry extension 的具体实现类型；
5. workflow extension 的最终模板格式；
6. adapter context manager 的压缩策略；
7. 不同角色之间 handoff packet 的字段细节；
8. audit 的严格程度；
9. pass@k 的具体 k 值；
10. 多模型实验何时加入。

这些应随实验过程动态调整。

------

## 25. 推荐的最小实现切入点

建议第一版不要试图一次实现完整系统，而是先完成以下最小闭环：

1. 一个自由 actor loop；
2. 一个 controlled corpus multi-hop QA 环境；
3. search/open/read 基础工具；
4. trace logger；
5. state snapshot；
6. prefix-fork；
7. 一个最小 registry；
8. 一个简单 Intervention hook；
9. 一个 patch submit 工具；
10. 一个 eval trigger；
11. 一个 changelog；
12. 一个最小 audit。

最小闭环的目标不是追求高性能，而是验证：

> 外部适配 agent 是否能从 actor 失败中发现某类可复现问题，并通过 registry patch 让 hard harness 在无外部强模型参与下取得可观测提升。

一旦这个闭环成立，再逐步加入更复杂的 memory、workflow extension、controller policy、schema repair、pass@k 统计和多模型实验。

------

## 26. 总结

本项目的核心价值不在于简单自动调 prompt，也不在于让强模型在线辅助弱模型，而在于探索一种面向小模型的 harness synthesis 范式：

1. 小模型 actor 保持固定；
2. 基础 agent core loop 保持不可变；
3. 外部强模型在离线阶段观察和软干预；
4. prefix-fork 用于验证指导有效性；
5. 有效指导被硬化为 registry extension；
6. 最终 harness 脱离外部强模型；
7. 系统通过 intervention rate decay 和 soft-hard gap closing 展示从软适配到硬化部署的过程。

如果实验成功，它可以回答一个很有实际价值的问题：

> 对能力有限的小模型而言，性能提升是否可以主要来自模型外部 harness 的自动适配，而不是直接训练模型或依赖在线强模型？

这个问题与真实业务中的低成本、低延迟、小模型 agent 部署高度相关，也能为后续小模型 search agent、工具 agent 和领域 agent 的工程设计提供参考。
