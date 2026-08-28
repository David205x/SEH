# TASK-007 Experience Summarizer 分层重构实施报告 v16

> 实施状态：已完成。最终代码、测试、真实 API A/B 与已知边界见
> `TASK-007_experience_summarizer_redesign_implementation_v1.md`；下文保留实施前的
> 计划基线，供核对设计到代码的对应关系。

## 当前状态

- 已完成 Experience Summarizer 的领域设计，确认 Capability 与 Direction 使用独立 Pass、独立 Packet 投影和独立输出协议。
- 已完成 Experience Observation Packet、Experience Detail、Evidence Structure、Research Scheme、Mechanism Scheme 与三层 Research Direction 的术语定义。
- 已完成 Capability/Direction Trigger 白名单、Direction update target、Researcher `scheme_action` 与 Researcher-first 回流规则的设计。
- 当前代码仍是组合式 `experience_summarizer@3`，同时处理 capability、direction 与 teacher work；其 Packet、工具和输出协议尚未迁移到新设计。
- 当前 Experience Summarizer 尚未自动挂入 Evolution Controller，也未接入 Experience Store。
- 工作区已有多项未提交修改和未跟踪文件；本任务在这些内容上增量实施，不重置或覆盖既有修改。
- 尚未执行本轮代码修改、定向测试和真实 Teacher API 验证。

## 任务意图

本任务将已确认的 [Experience Summarizer 重构设计](../../docs/design/experience-summarizer-redesign.md) 实现为可独立验证的 Draft 提炼链路，并补齐该链路依赖的三层身份、Researcher 路由、Trigger、Packet 与 Detail 机制。验证产物只形成 Experience Draft Artifact，不在本任务中实现 Draft Settlement 或正式 Experience Store 消费。

本任务直接服务 Goal H3：

> “将已结算轨迹中的 typed verification verdict 与终态转为有 provenance、严格 consumer/scope、可失效和可复查的 role-scoped experience，能够减少跨 attempt/generation 的能力越界、同角色错误复发和方向重走，并提高单位总预算的 useful Candidate yield，同时控制 false pruning 与 held-out utility。”

相关路由修改保持 H1/H2 的既有 Evidence 与 Hook Feasibility 语义：

> H1：“在持久化 Candidate 物化前，冻结真实 Student Prefix 上的 matched no-op 与不可部署 soft intervention 证据能够预测 downstream Candidate effect，并在预算匹配下提高 useful Candidate yield、减少无效完整评估。”

> H2A：“对 Student-owned recognition、decision、adherence、fallback 与 parse responsibility 的独立 probe 能够预测未参与 probe 的真实 Prefix 上的 shadow/in-loop realizability。”

> H2B：“基于逐职责 realizability 证据在 reject、simplify、deterministic lowering 与 ownership reassignment 之间进行 adaptive routing，相对固定 ownership 策略能够提高可实现且有用的 Candidate 产出并减少浪费。”

## 实施思路

### 两个独立 Summarization Pass

将现有组合角色拆为 Capability Summarization Pass 与 Direction Summarization Pass。两个 Pass 共享来源 Artifact，但各自拥有 Prompt、Role Contract、预算、Detail Registry 和 Role Artifact；一个 Pass 失败不影响另一个已完成的 Draft。

Capability Pass 只形成狭窄 Student/Hook-model 行为边界。Direction Pass 只更新程序维护 Research Direction 中的 Failure Direction、Research Scheme 或 Mechanism Scheme。Teacher Work 不进入两个常规 Pass。

### 三层 Research Direction

Controller 维护：

```text
Failure Direction
└── Research Scheme
    └── Mechanism Scheme
        └── Candidate Attempt
```

Failure Analyst 每次成功提交创建新的 Failure Direction。Researcher 使用 `revise_current`、`start_new` 或 `reanalyse_failure` 表达方案谱系关系，Controller 创建或继承 Research Scheme。首次成功 Distillation 创建 Mechanism Scheme，后续 MechanismSpec revision 保留同一 Scheme 身份并增加 revision。历史 Artifact 不覆盖。

### Researcher-first 回流

研究层下游负向结果先回到 Hypothesis Researcher。Researcher 可以继续修订当前方案、在同一 Failure Direction 下开始平行方案，或请求 Failure Analyst 建立新方向。Candidate rejection 不再默认直接调用 Failure Analyst。

### Trigger-specific Packet

为每个 Capability/Direction Trigger family 建立 Source Adapter。Adapter 从当前 Work Item、Control Journal 和已附着 Artifact 直接投影 Observation、Validity、Evidence Structure 与 Detail Directory。来源无法提供硬条件时不调用对应 Pass；预期 Artifact 缺失或损坏时报告数据完整性错误。

控制器事件名不直接进入模型 Packet。Prompt Assembly 根据本次实际处理过程插入 Source Processing Context，解释已完成测试、Review/Gate outcome 的证据含义与上限。

### 单一 Detail 工具

使用 `inspect_experience_detail(detail_id: int)` 读取一个授权 Detail。Detail Projector 确定性生成内容，不调用二次总结模型。工具不设置固定总读取数量上限，同一 Detail 禁止重复读取，整体调用受角色 turn/token 预算约束。

### Draft 输出

Capability 模型输出 `evaluated_behavior`、`observed_limitation`、`conditions` 和局部 Observation refs。Direction 模型输出 `evidence_update`、自由文本 `disposition`、`revisit_condition`、`applicability` 和局部 Observation refs。程序附加类型、三层 Direction Context、Evidence Structure 与 provenance，并把局部编号解析为稳定 Evidence 引用。

## 计划实现

### 身份与 Controller 路由

- 修改 `search_harness/evolution/identifiers.py`：增加 Research Scheme 与 Mechanism Scheme 的稳定 ID 生成函数。
- 修改 `search_harness/evolution/control/domain.py`：在 lineage/payload 的现有持久化边界中保存三层身份与 revision，不建立独立 Store。
- 修改 `search_harness/evolution/control/transitions.py`：
  - Failure Analyst 每次成功提交创建新 Failure Direction；
  - Researcher 按 `scheme_action` 创建 revision、新 Scheme 或路由 Analyst；
  - Distillation 创建/修订 Mechanism Scheme；
  - Candidate rejection 与其他研究层回流先进入 Researcher；
  - 从 typed route 派生明确的 Capability/Direction Trigger Event；
  - Candidate review 与 Promotion Gate 对同一 Candidate 只产生一个末端 Direction 事件。
- 修改 `search_harness/evolution/control/controller.py`、`effects.py` 和必要的 journal/event 投影，使新身份、Trigger 与 Draft Artifact 可恢复且不重复执行已完成工作。

### Role Contract 与模板

- 修改 `search_harness/evolution/research/roles/contracts.py`：
  - 为 Researcher continuation 增加 `scheme_action` 分支；
  - 删除组合 Experience Summary 的固定 Capability taxonomy 与 Teacher Work 输出；
  - 增加 Capability/Direction Packet 和 Draft 输出类型；
  - 注册两个独立 Role Definition。
- 新建或迁移 `harness_templates/teacher/capability_summarizer/` 与 `harness_templates/teacher/direction_summarizer/`：分别提供 system/user Prompt、Detail 工具和 terminal output component。
- 删除正式路径对 `harness_templates/teacher/experience_summarizer/` 的依赖；验证完成前保留旧文件用于结果对照，迁移完成后删除较差实现。
- 修改 `config/runtime.yaml`：增加两个 Role 的独立 thinking、turn、token 和 retry 配置，初始值沿用当前 Experience Summarizer 的同类配置后再由真实 API 结果调整。

### Packet、Source Adapter 与 Detail

- 重构 `search_harness/evolution/research/experience_summary.py`：
  - 定义公共 Observation、Validity、Evidence Structure、Open Check 与 Detail Directory；
  - 定义 Capability/Direction 专用 projection；
  - 实现 Trigger family 的 Source Adapter；
  - 实现 Research Direction Context 的固定投影；
  - 实现 Detail Registry、单次读取和 output refs 校验。
- 修改 `search_harness/evolution/research/resources/base.py`：绑定两个独立 Packet 与 Detail Registry，并向 Prompt 暴露各自的模型视图。
- 修改 `search_harness/evolution/research/tools.py`：用 `inspect_experience_detail(detail_id)` 替换旧 `inspect_experience_evidence(evidence_ref, view, selectors)`。
- 修改 `search_harness/evolution/research/roles/native_chat_runner.py`、`agents_sdk_runner.py` 与 `role_execution.py`：支持两个独立 Pass 的 Prompt Assembly、terminal output、失败 Artifact 和已完成结果复用。

### Trigger Source

- Capability：接入 Hook Feasibility research revision、满足重复结构的 Evidence Review revise/reject，以及包含重复 evaluator mismatch 的 Conformance revise。
- Direction：接入 Evidence Review、Distillation、Hook Feasibility、Compiler、Conformance evidence/mechanism route、Candidate Review evidence/mechanism/reject 与 Promotion Gate passed/failed。
- Candidate Validation、unchanged rejected Candidate 和 implementation-only revision 不调用两个 Pass。

### 文档

- 实现完成后更新 `docs/architecture/evolution.md`，替换组合 `experience_summarizer@3` 的当前架构描述。
- 更新 `docs/reference/role-contracts.md` 和 `docs/reference/artifact-schemas.md`，记录两个 Role Contract、Packet、Detail Tool、三层身份和 Draft Artifact。
- 如增加运行配置字段，同步更新对应 runtime 配置 reference。

### 测试与真实 API 验证

- 扩展 `tests/evolution/research/test_experience_summary.py`：覆盖 Packet 来源、unknown/not-applicable、Detail 授权、重复读取、Capability/Direction output refs 与空结果。
- 扩展 `tests/evolution/test_control.py`：覆盖三层身份创建/继承、Researcher 三种 `scheme_action`、Researcher-first 回流、Trigger 唯一性与 resume。
- 扩展 Role loader/runner 测试：覆盖两个模板可发现、schema 可提交、失败 Artifact 持久化和独立 Pass 复用。
- 先使用现有 Artifact 构造 shadow 请求，不调用 Student。
- 对代表性 Capability 与 Direction Packet 分别并行调用真实 Teacher API 三次；若结论或结构稳定性分歧明显，扩展到五次。
- 验证输出原子性、证据引用、Detail 读取、Direction target、空结果行为和 token 用量。
- 本轮不运行全量历史测试；运行受影响模块的 rooted `unittest discover` 与必要 smoke test。

## 盘点结果

- `ExperienceSummaryTrigger` 当前声明 12 个混合触发，包含 Capability、Direction 和 implementation-only 事件；拆分后的 Pass 需要独立 Trigger 集合。
- `ExperienceSummaryInput` 当前使用 `trigger`、`route_target_role`、`direction`、`attempt` 和调用方组装的 `evidence`；它没有 Trigger-specific Artifact adapter。
- `ExperienceEvidenceStore` 当前以 `evidence_ref/view/selectors` 查询，并设置每次最多三项与总调用熔断；新设计改为 Packet 内整数 Detail 目录。
- 当前 Capability 输出要求固定 `decision_scope`、四类 `capability_area` 与模型回填 `elicitation_scope`，与已确认的开放 `evaluated_behavior` 冲突。
- 当前 `CandidateComparisonStore` 已提供 paired changes、指标、paired trajectory 与 outcome digest，可直接作为 Candidate/Promotion Direction Source。
- Hook Feasibility Artifact 已保存真实 system/user input、thinking mode、repetition、expected/observed label 和原始输出，是 Capability Source 中信息最完整的触发。
- Conformance Finding 已保存 failure layer、expected/observed label、decisive input 与 typed route；只有 evaluator mismatch 适合作为 Capability Source，evidence/mechanism route 适合作为 Direction Source。
- 当前 Candidate rejection 通过 `_new_research_attempt()` 直接创建 `ANALYZE_FAILURE` Work Item，并把 `prior_problem_direction_id` 交给下一次 Analyst；当前 Researcher 没有路由 Analyst 的输出分支。
- `problem_direction_id` 当前是 generation-local 身份；项目尚无 `research_scheme_id` 和 `mechanism_scheme_id`。
- Teacher Role Artifact 外壳已保存 role/model、schema、Model Input digest 和 resource artifacts，因此 Packet 不需要重复身份和 digest 字段。
- 工作区包含本任务前已有的 Controller、Role、Versioning、实验脚本和文档修改；实施必须逐文件核对现有 diff，避免覆盖这些修改。
