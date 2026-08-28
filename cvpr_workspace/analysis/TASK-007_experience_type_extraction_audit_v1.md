# TASK-007 三类 Experience 定义与提取审计

## 1. 审计结论

当前实现不足以稳定说明三类 Experience “是什么、由什么证据产生、应写成什么形态”。v10 增加完整职责/转移上下文和结构化因果事实后，能改善 causal owner 判断，但仍缺少以“结论对象”为核心的类型判定规则，因此不能直接批准实施。

## 2. 当前 Prompt 与输入

当前 Prompt 对三类经验的定义分别是：

- `student_capability`：有效输入进入 faithful implementation 后，由重复、受控或多个直接行为证明的能力或稳定性边界。
- `teacher_work`：只面向 `route_target_role` 的可执行修正。
- `experiment_direction`：可复用的研究或评测设计变化。

这些定义已经提供基本方向，但存在四个缺口：

1. 没有说明每类经验的结论对象：Student/Hook Model、某个 Teacher Role 的工作，还是与执行者无关的研究方向。
2. 没有规定每类 lesson 必须包含哪些事实成分。
3. 没有给出三类同时看似成立时的优先级和互斥条件。
4. `teacher_work` 只检查是否存在 `route_target_role`，没有要求 causal owner 确实属于该角色职责。

当前输入的 `evidence` 是自由字符串。`direction`、`attempt` 和 evidence 可能包含 outcome、control、实现保真、数据混杂与责任主体，但这些语义没有固定位置。模型需要先自行恢复因果结构，再判断经验类型。

## 3. v10 仍未解决的边界

v10 计划加入角色职责图、负向 Transition、experience consumer，以及 `outcome/comparison/boundary`，但其 Prompt 方案仍以“因果层”作为主要分类方法。因果层不足以唯一决定经验类型：

- Hypothesis Researcher 提出不可满足的成功条件，既可能被写成该角色的 `teacher_work`，也可能被写成跨角色有效的 `experiment_direction`。
- Hook Model 在错误 Candidate 输入上失败，既可能被误写成 `student_capability`，也可能实际属于 Compiler 或 Mechanism 的输入/实现问题。
- 一个 faithfully implemented 方向相对 control 没有 differential effect，说明方向未被支持，不等于 Student 缺少能力。
- Candidate activation 只落在 contract negatives，可能证明模型判别边界，也可能只证明机制正例定义或实验方向错误，必须先确定结论对象。

## 4. 建议的规范定义

### 4.1 Student Capability Experience

结论对象是冻结 Student 或 Hook Model 在明确输入、任务、模式和决策边界下的能力或稳定性，不是 Candidate、Prompt patch、Compiler 实现或研究方向。

必需证据：

- contract/input 有效；
- 实现或 probe 投影 faithful；
- 重复、matched control 或多个直接模型行为支持同一边界；
- 上游设计、数据充分性和实现错误不能更直接解释结果。

Lesson 必须包含：模型主体、有效条件、重复或对照行为、被证明的窄能力边界，以及该边界对后续方案的操作含义。

Applicability 必须限定：Student/Hook 使用场景、输入或任务边界、thinking mode 或其他实际相关条件。

### 4.2 Teacher Work Experience

结论对象是某个具体 Teacher Role 在其职责、Role Contract 和有效输入下完成工作的方式，不是该研究方向本身是否值得继续。

必需证据：

- causal owner 与 `route_target_role` 相同；
- 失败事实违反 Attribution Context 中该角色拥有的职责；
- 输入或上游合同足以让该角色完成职责；
- 可以形成该角色下次执行时可检查的具体义务。

Lesson 必须包含：角色拥有的职责、实际违反点、造成的后果，以及下次工作的具体步骤或验证义务。

Applicability 必须限定：相同角色职责、合同和工作情境。若 causal owner 不等于 route target，不生成 `teacher_work`。

### 4.3 Experiment Direction Experience

结论对象是与具体 Teacher 身份无关的研究方向、因果假设、机制类别、证据采集或评测设计。它回答“后续应该继续、停止、缩窄或怎样验证这一类方向”。

必需证据至少满足一种：

- treated behavior 相对 control 无 differential effect；
- clean falsifier 否定方向；
- harmful over-trigger 或稳定回归表明方向条件过宽；
- corpus/data sufficiency 或 evaluation design 使结论混杂；
- Candidate comparison 表明收益不由机制 activation 产生，或成本/回归使方向不值得原样继续。

Lesson 必须包含：被检验方向或设计、证据如何支持/否定/混杂该方向，以及未来研究选择或验证义务。

Applicability 必须限定：机制类别、问题条件或评测设置，而不是某个 Teacher Role 的单次工作。

## 5. 类型选择规则

先判断“经验在描述谁或什么”，再判断因果层：

| 判定问题 | 经验类型 |
| --- | --- |
| 结论是否是冻结 Student/Hook 在有效输入与 faithful 投影下的重复能力边界？ | `student_capability` |
| 结论是否是 route target Teacher 在其职责内的具体工作缺陷，且换一个研究方向仍应遵守同一义务？ | `teacher_work` |
| 结论是否关于研究方向、因果假设、机制类别、控制组、证据充分性或评测方法，并且换一个 Teacher 执行仍成立？ | `experiment_direction` |

默认只输出一个主要类型。只有结论对象不同、事实依据不同、未来义务也不同，才允许第二种类型。不能把同一修复分别改写成 capability、teacher work 和 direction 来填满 taxonomy。

## 6. 输入应支持的提取信息

不需要增加顶层字段。计划中的五字段应满足以下语义：

- `direction`：被检验的因果主张或机制方向，以及预期行为。
- `attempt`：实际执行者/机制、施加方式、覆盖条件和已知有效性。
- `evidence.*.outcome`：明确写出观察主体、行为和直接后果。
- `evidence.*.comparison`：写出比较的两侧及差异、重复模式或 activation-attributed effect；没有则为空。
- `evidence.*.boundary`：写出已经确认的输入、合同、实现、数据或环境边界，以及尚未解决的混杂；没有则为空。

Attribution Context 负责说明角色职责、Transition 和 Experience consumer；Evidence 工具只补足初始输入尚未建立的因果链。

## 7. 具体案例校验

- 空 passage 进入 classifier：观察对象是 Compiler data flow，属于 `teacher_work`，不是 Student capability。
- 相同有效 probe 在 thinking mode/repetition 下反复翻转：观察对象是 Hook Model 能力边界，属于 `student_capability`。
- generic patch 相对 untreated control 无差异：观察对象是干预方向的因果主张，属于 `experiment_direction`。
- corpus sufficiency 未验证导致 success condition 不可判：若结论是该方向的试验不可解释，属于 `experiment_direction`；只有独立证据证明 Hypothesis Researcher 在有效信息下违反其角色工作义务时，才另生成 `teacher_work`。
- Compiler 原样重交被拒实现：观察对象是 Compiler 工作过程，属于 `teacher_work`。
