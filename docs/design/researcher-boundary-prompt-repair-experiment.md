# Shadow Hypothesis Researcher Prompt 修复实验

状态：待实施  
日期：2026-08-13  
前序实验：`runs/experiments/researcher_boundary_prompt/20260813_023954`

## 1. 目标

本轮直接承接前序实验，只验证四项改动：

1. 修复 Researcher 保住时间边界后，仍可能把 Analyst 已确认的具体错误机制扩大为上位类别的问题。
2. 压缩 Boundary Prompt，保留其已验证有效的边界语义，同时降低模型请求、工具调用和 token 成本。
3. 删除 Researcher 自动评分器，所有语义结论统一来自匿名语义复核。
4. Researcher 阶段通过后，调用现有 Teacher API 和 Student API，实际运行 Intervention Executor、Trial Reviewer 与 Evidence Reviewer，验证 Hypothesis 是否转化为正确激活、Student 行为变化和可审查证据。

本轮继续只修改实验 shadow Researcher 和一次性实验编排。正式 Researcher 模板、正式协议与生产 Controller 不在本轮迁移范围内。

## 2. Prompt 修复

### 2.1 保留已经生效的语义

以上一轮冻结的 Boundary Prompt 为基线，保留以下控制逻辑：

- 区分失败前兆、决定性失败和同前兆自然恢复状态。
- 纠正性方案只能在决定性失败事实已经可观察时触发。
- 早于决定性失败的方案必须明确声明为预防性风险干预，并要求观察同前兆自然恢复或不必要激活。
- Intervention Executor 只判断冻结的 `activation_condition` 并执行 `instruction`，不会替 Researcher 收窄条件。
- 不推断 Failure Direction 没有提供的数据集比例、排除项或 corpus 覆盖。

### 2.2 修复最小失败谓词保持

Prompt 应把 Analyst 的 `pattern`、`applicability` 和 `caveats` 合并解释为一个**最小已确认失败谓词**。Researcher 必须先识别其中不可删除的决定性限定，再选择 phase 和 intervention。

具体要求：

- `activation_condition` 必须保留已确认机制中的决定性限定。例如 Analyst 只确认了“把未检索实体断言为 zero/absent”，Researcher 不得改写为“任何单边证据后的确定性比较”。
- `caveats` 中被标记为机制混杂、仅表面相邻、未确认或不统一的案例，不得转为正向触发范围或正向证据义务。
- 时间扩宽和错误类型扩宽分开处理。把触发提前到前兆状态属于预防性主张；把具体错误替换成更一般的错误类别属于新的机制主张。后者没有 Analyst 证据时不得发生。
- 若 Researcher 有意研究更宽机制，必须把超出已确认谓词的部分保留为未知或后续研究对象，不能在当前 Hypothesis 中直接视为已支持。

提交前检查应包含一个简短的谓词对照：逐项确认 Analyst 的决定性事实仍出现在 `activation_condition`、`applicability` 或明确限制中，并确认没有把 caveated analog 纳入正向范围。不新增协议字段，判断落实到现有字段。

### 2.3 明确允许的 Student 提示干预面

在读取 Student Behavior Interface 和 Intervention Capability 后，Researcher 可以把现有 Student-visible `system`/`developer` 提示内容视为合法干预面；当 `post_prompt` 与 context patch 能力支持时，可以提出有界提示修订。

Prompt 应同时要求：

- 把提示修订、运行时反馈和控制语义视为并列候选，选择能够实现当前 Hypothesis 的最小改动。
- 无条件提示规则必须有与其全局影响范围相符的证据；局部错误机制不得直接改写成对所有案例生效的全局规则。
- 条件式提示 patch 的触发仍由 `activation_condition` 约束，不能假设 Executor 会额外判断是否需要帮助。

该说明只明确已有能力，不修改 `InterventionHypothesis` 协议，也不预设本轮每份 Hypothesis 都必须选择提示词干预。

## 3. Prompt 成本压缩

对 Boundary Prompt 做整体压缩，不在尾部继续增加补丁段落。建议结构为：

1. `Objective and handoff semantics`
2. `Boundary decision procedure`
3. `Required procedure`
4. `Output contract`
5. `Revision continuation`
6. `Before submitting`

压缩原则：

- corrective/preventive、precursor/decisive failure、natural recovery 各只完整定义一次。
- 字段说明只说明定义如何落入字段，不重复角色原则。
- `Before submitting` 使用短检查项，不重新解释正文。
- 保留工具读取义务、能力查询、协议约束、长度限制、泄露禁令和 continuation 语义。
- 删除不会改变角色决策的解释性例句和同义重复。

成本验收同时看静态 Prompt 和实际角色运行：

- 修复版 `system.md` 字符数不高于上一轮 Boundary Prompt 的 80%。
- 在相同输入、模型配置、seed 和预算下，修复版平均 total tokens 至少比上一轮 Boundary 降低 15%。
- 平均 requests 和达到 completion token 上限的调用数不得增加。
- 成本下降不得以减少必要的轨迹、Student Behavior Interface 或 capability 读取为代价。

如果语义门禁通过但 token 降幅不足，只判定 Prompt 修复有效、成本优化未完成；不得为达到成本指标删除已证明必要的边界控制。

## 4. Researcher 实验输入与变体

### 4.1 变体

- `Boundary baseline`：冻结使用前序实验的 Boundary Prompt 和既有 Role Artifacts；已有输入不重复调用 API。
- `Repair`：本轮压缩并修复后的 shadow Researcher Prompt。

新输入若不存在可复用的 Boundary baseline，则对 baseline 和 Repair 使用完全相同的输入、模型配置、seed、预算和角色工具，各运行 3 次。

### 4.2 输入

保留三个职责不同的冻结输入：

- **纠正性回归输入**：复用前序 `input_01`，确认修复和压缩没有破坏已经稳定的 absence-based `pre_final` 边界及自然恢复排除。
- **具体机制保持输入**：复用前序 `input_03`，主要检查 `zero/absent` 机制没有扩大成任意 definitive one-sided comparison，混入 confabulation 的 analog 仍保留为限制。
- **预防性能力输入**：准备一份已有轨迹证据明确支持“前兆状态本身是待研究风险”的冻结 Failure Direction。它必须同时包含目标风险后续失败、同前兆自然恢复或无需干预的对照，使 Researcher 可以合法形成预防性 `post_tool` 方案和相邻证据义务。输入由语义复核确认后冻结，不从期望输出反向写入实体、答案或具体 intervention 指令。

不得仅为了获得 phase 多样性而要求 Researcher 选择 `post_tool`。每份输出按其冻结 Failure Direction 判断；合理的多个 `pre_final` 不自动失败，合法的 `post_tool` 也不自动加分。

Repair 对三个输入各运行 3 次。前两个输入与前序冻结 Boundary 产物配对；预防性输入对 Boundary baseline 和 Repair 各运行 3 次。

## 5. 删除自动评分器，统一语义复核

### 5.1 代码与产物清理

从 `experiments/run_researcher_boundary_prompt_experiment.py` 删除：

- `score-researcher` 命令及其模型配置参数。
- `_AUTO_REVIEW_PROMPT`、`score_researcher()`、`_validate_review()` 和只服务于自动评分的解析逻辑。
- `automatic_review.json`、`automatic_review.raw.json`、`scorer.stdout.log`、`scorer.stderr.log` 的生成与汇总依赖。
- 对应自动评分单元测试和文档说明。

保留匿名化、固定随机化和协议确定性校验。将 Researcher 复核产物统一命名为 `semantic_review.json`，不再同时维护 `automatic_review` 与 `manual_review` 两套结论。

### 5.2 语义复核内容

`prepare-semantic-review` 生成匿名包；复核者看不到变体身份、usage、transcript 或路径。每项 `0/1` 判断必须引用 Failure Direction 与 Hypothesis 中的具体文本并给出简短理由：

- `minimum_failure_predicate_preserved`：最小已确认失败谓词及关键 caveat 没有被删除或上位化。
- `temporal_observability`：触发事实在所选 phase 均可观察。
- `claim_phase_alignment`：纠正性/预防性主张与 phase 一致。
- `neighbor_falsifiability`：自然恢复、安全不确定性和机制混杂 analog 被正确放在激活边界内外。
- `worker_semantics`：没有依赖 Executor 自主收窄触发。
- `scope_discipline`：没有增加未支持的比例、排除项、corpus 覆盖或全局适用性。

语义复核是 Researcher A/B 和进入 Intervention 阶段的唯一内容判定来源。程序只负责：

- 校验 Role Artifact 与协议是否合法；
- 校验匿名映射、哈希和复核 JSON 结构；
- 根据冻结的语义复核结果计算门禁；
- 不再调用另一个模型自动替代语义复核。

## 6. Researcher 阶段门禁

Repair 进入下游必须同时满足：

- 9/9 输出协议合法且无案例实体、答案或命名 query 泄露。
- 纠正性回归输入至少 2/3 六项全通过，且相对前序 Boundary 无关键维度回退。
- 具体机制保持输入至少 2/3 六项全通过，3/3 通过 `minimum_failure_predicate_preserved`。
- 预防性输入至少 2/3 六项全通过；通过产物必须明确把早期触发声明为预防性风险主张，并包含同前兆自然恢复或不必要激活义务。
- 所有输出均通过 `temporal_observability` 与 `worker_semantics`。
- 静态 Prompt 成本目标达到；运行 token 目标单独报告，不与语义正确性相互抵消。

门禁不要求三种输入选择不同 phase，只要求每种选择与其 Failure Direction 和证据义务一致。

## 7. Intervention 与 Reviewer 实测

Researcher 门禁通过后，允许使用当前环境已配置的 Teacher API 和 Student API。API 密钥只从现有环境配置读取，不写入产物。

### 7.1 冻结 Hypothesis

按匿名语义复核后的固定规则选择：

- 一份具体机制保持完整的纠正性 Hypothesis；
- 一份完整通过的预防性 Hypothesis。

每类选择最早通过全部六项的 repetition；选择后记录内容哈希，不因下游结果改选。若某类不存在合格产物，则停止，不用较差产物补位。

### 7.2 Assignment 组成

每份 Hypothesis 使用相同职责的逻辑案例集合，并对每个逻辑案例运行 3 个 replicate：

- 已观察到目标失败的正向案例。
- 共享前兆但会自然继续检索、正确完成或安全表达不确定性的邻近案例。
- 已经查询双方或已经具备充分证据、因此不应激活的案例。
- 与目标表面相似但包含不同错误机制的 analog。
- 必要时加入一项稳定正确但会触发宽泛规则的成本/扰动案例。

Selector 和实验清单只向程序提供案例身份与 prefix；Intervention Executor 不得看到正负标签、参考答案或期望动作。Assignment 采用 phase-compatible prefix；无法到达所需 phase 时记为 `not_reachable`，不临时换案例。

### 7.3 角色执行

按以下顺序运行：

1. Intervention Executor 使用冻结 Hypothesis 和 Assignment 判断 `positive/negative/uncertain` 并执行或保持不变。
2. Student API 从干预后的分支继续运行到终态，保存实际激活、Student-visible mutation、tool calls、final answer、score 和 usage。
3. 每个 Trial 调用正式 Trial Reviewer，判断条件匹配、instruction fidelity、预期即时效果、case leakage 和行为扰动。
4. 同一 Hypothesis 的全部 Trial Review 完成后，调用正式 Evidence Reviewer，判断证据是否支持、需要修订或不足，并输出对 Researcher 可执行的结构化 assessment。

本轮固定使用一个 Intervention Executor thinking 配置，不再同时引入 thinking A/B。Teacher/Student 模型、temperature、seed、预算和 Reviewer 配置在两个 Hypothesis 及各 replicate 间保持一致。

### 7.4 下游判定

最终语义复核同时查看 Hypothesis、Trial traces、Trial Reviewer 和 Evidence Reviewer 产物，分别报告：

- 正向 Trial 的激活率和 immediate expected effect 成功率。
- 自然恢复、安全不确定性、双方已检索和异机制 analog 的非激活率。
- 激活后 Student 是否产生目标行为，以及 final score、tool calls、steps 和 token 的变化。
- Reviewer 是否识别误激活、条件不匹配、自然恢复被扰动和机制泛化。
- Evidence Reviewer 的 decision 是否由实际 Trial 证据支持，反馈是否足以指导一次 Researcher 修订。

Researcher Prompt 的成功不能仅由 Reviewer 给出 `approve` 认定。至少需要：

- 每份 Hypothesis 覆盖不少于 2 个 distinct positive 逻辑案例；若现有证据只有 1 个，明确记为案例内因果验证，不外推泛化。
- 目标正向 Trial 中多数满足冻结的 immediate expected effect。
- 所有关键邻近类别至少各有 1 个 distinct example，且没有系统性误激活。
- Evidence Reviewer 的结论与最终语义复核一致；不一致时保留分歧并分析 Reviewer，而不是覆盖语义复核。

## 8. 实现位置与命令

优先继续使用并修复：

- `experiments/teacher_query_views/templates/hypothesis_researcher/prompt/system.md`
- `experiments/run_researcher_boundary_prompt_experiment.py`
- `tests/experiments/test_researcher_boundary_prompt_experiment.py`

实验入口至少提供：

- `prepare-repair`
- `run-researcher-repair`
- `prepare-semantic-review`
- `summarize-researcher`
- `prepare-intervention`
- `run-intervention`
- `review-trials`
- `review-evidence`
- `summarize`

所有产物写入：

`runs/experiments/researcher_boundary_prompt_repair/<timestamp>/`

至少包含冻结输入、baseline/repair Prompt 哈希、Researcher Role Artifacts、匿名包、`semantic_review.json`、Intervention Assignment、Trial traces、Trial Review、Evidence Review、`summary.json` 和 `report.md`。

## 9. 最低测试与停止条件

最低测试覆盖：

- 正式 Researcher 模板在 prepare 和运行后哈希不变。
- 自动评分命令、提示常量和自动评分产物依赖已删除。
- 匿名映射可逆且语义复核结构缺项时 fail fast。
- 最小失败谓词检查夹具能够区分 `zero/absent` 与更宽的 definitive comparison。
- caveated analog 不会被汇总成正向证据。
- Researcher 门禁失败时无法启动 Intervention。
- Hypothesis 选择、Assignment 顺序和 prefix 解析可重复。
- Teacher/Student API 运行记录实际模型配置但不记录密钥。
- Trial Reviewer 与 Evidence Reviewer 使用各自正式协议，缺失或协议错误不得计作通过。

出现以下情况立即停止当前阶段并保留产物：

- 修复需要改变正式协议、角色职责或 Reviewer 判据；
- 找不到有轨迹证据支持的预防性 Failure Direction；
- Researcher 仍把 input 3 的具体机制稳定扩大为上位类别；
- API 配置未实际生效、Assignment 泄露标签或 prefix 与 Hypothesis phase 不兼容；
- Reviewer 结论只能通过放宽冻结 Hypothesis 或证据标准才能成立。

最终报告按时间线区分 `[角色]` 和 `[机制]`，分别报告 Prompt 语义改善、成本变化、Intervention 行为效果和 Reviewer 判断，不把单案例结果外推为全局可靠性。
