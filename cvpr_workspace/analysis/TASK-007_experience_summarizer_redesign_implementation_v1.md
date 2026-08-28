# TASK-007 Experience Summarizer 重构实施与验证报告 v1

## 实施结果

本轮已按 `docs/design/experience-summarizer-redesign.md` 将组合式
`experience_summarizer@3` 替换为两个独立角色：

- `capability_summarizer@1` → `capability_summary@1`；
- `direction_summarizer@1` → `direction_summary@1`。

旧正式模板已删除。两个新角色共享确定性的 Experience Observation Packet 与
`inspect_experience_detail(detail_id)`，但使用独立 Prompt、输出合同、Role Run、预算与
Artifact。当前输出仍是 Experience Draft Artifact，不执行 Draft Settlement、合并或
Experience Store 写入。

## 核心改动

### Packet 与 Detail

- Observation 固定包含 subject、expected、observed、comparison、conditions、四类
  validity、evidence structure 和 open checks。
- Detail Directory 只暴露数字 ID、所属 Observation、可解决的证据缺口、覆盖范围与
  一句话说明；正文由来源专用 projector 确定性生成。
- 同一 Detail ID 禁止重复读取；删除“最多读取三项”的旧限制，保留 20 次安全熔断和
  Role 自身的 turn/token 预算。
- Output validation 只接受当前 Packet 中的 Observation 数字引用；Capability 禁止完全
  重复项，Direction 最多一项。

### 三层身份与 Researcher-first 路由

- 新增 Failure Direction、Research Scheme 和 Mechanism Scheme 的稳定 ID。
- 身份与 revision 保存在 Work payload，避免破坏旧 Journal 的 TrajectoryLineage
  反序列化。
- Hypothesis Researcher 升级为 `hypothesis_researcher@2`，输出
  `scheme_action + hypothesis`：初始调用必须 `start_new`；continuation 可以
  `revise_current`、`start_new` 或 `reanalyse_failure`。
- Candidate reject、Promotion Gate failed、unchanged rejected Candidate 与
  `not_distillable` 不再默认直接调用 Analyst，而是先回流 Researcher；只有
  `reanalyse_failure` 建立新的 Failure Direction。
- 成功 Distillation 建立或继承 Mechanism Scheme；后续 spec revision 保留其 ID。

### Controller 挂载

- Capability/Direction 以独立旁路 Work 挂在原 typed transition 之前；原 Work 的
  revision、settlement、promotion 和 rejection 语义不被替换。
- Capability 来源：Hook Feasibility `needs_research_revision`；重复、非 parse-error 的
  Conformance evaluator mismatch；Evidence Review 来源只有具备直接模型行为证据时才
  可形成 Packet，当前聚合 Trial Review 不满足时确定性返回 not eligible。
- Direction 来源覆盖 Evidence Review、Distillation、Hook Feasibility、Compiler、
  Conformance 的 evidence/mechanism route、Candidate Review 的 evidence/mechanism/reject
  与 Promotion Gate passed/failed。Validation 与 implementation-only revision 不触发。
- Summarizer provider/结构失败写入独立 failure Artifact，并结束该旁路 Work，不伪造
  Draft，也不改变主路由。

## 定向测试

最终受影响测试集合共 96 项，全部通过：

```text
tests.evolution.test_control
tests.evolution.test_research_role_effects
tests.evolution.test_identifiers
tests.evolution.research.roles.test_contracts
tests.evolution.research.roles.test_loader
tests.evolution.research.roles.test_native_chat_runner
tests.evolution.research.roles.test_agents_sdk_runner
tests.evolution.research.test_experience_summary
tests.evolution_observer.test_timeline
```

另增加三层 ID、Researcher action 组合、同 Scheme revision、平行 Scheme、reanalysis、
真实 Hook probe adapter、真实 Conformance mismatch adapter、Detail 重复读取及多于三项
读取的覆盖。未运行与本次修改无关的全量历史测试。

## 真实 Teacher API 验证

模型为 runtime 配置中的 `deepseek-v4-flash`，输入来自既有 Artifact；每个输入并行重复
三次。没有调用 Student 或 Intervention Worker。

| 实验 | 配置 | 成功率 | 总 token | 结论 |
|---|---|---:|---:|---|
| v1 初始双角色 | thinking on, 8192/12 | 9/9 | 146,348 | 三类方向正确；负向 Direction 有字段超长修复 |
| v2 Prompt 收口 | thinking on, 8192/12 | 6/6 | 124,447 | Capability 聚合改善；负向 Direction 仍有 reasoning/修复波动 |
| v3 thinking A/B | thinking off, 8192/12 | 5/6 | 450,021 | 明显更差；一例耗尽 12 回合 |
| v4 难例预算化 | thinking on, 4096/8 | 3/3 | 38,125 | 负向 Direction 三次同向，无 Detail 读取与长度修复 |
| v5 其余最终配置 | thinking on, 4096/8 | 6/6 | 33,809 | Capability 与正向 Direction 均成功 |

最终采用 `thinking_mode: enabled`、`max_tokens: 4096`、`max_turns: 8`。最终配置合计
9/9 成功、71,934 token。Promotion failed 三次都把结论限制在当前 Mechanism Scheme
实现，不否定上游 Failure Direction；Promotion passed 三次都形成一条受测试范围约束的
正向 Direction Draft。Capability 三次都识别 disabled thinking 下的稳定 false positive
与 enabled thinking 下的同输入翻转，但在合并为一条 Draft 与拆成两条 Draft 之间仍有
原子粒度差异，没有发生结论翻转。

Researcher 新包装协议另使用同一历史 Failure Direction 并行验证三次，3/3 均合法提交
`scheme_action=start_new` 和完整 Hypothesis；总 token 439,353。该实验只证明真实模型能
遵守新结构，不证明所提方案质量，也显示 Researcher 原有多证据读取与 thinking 成本仍高。

## 已知边界

- Capability 的原子拆分粒度仍可能在一条综合行为边界与两条 mode-specific 边界间变化；
  两者引用同一 Observation，后续 Store settlement 需要决定合并规则。
- Direction thinking-on 偶尔会产生无工具调用的长 reasoning；4096/8 已限制单轮和回合
  上限，但没有消除 provider 延迟与 token 方差。
- Evidence Review 的现有 Trial Review 主要描述 intervention predicate 与效果，不恒定
  提供可归因的直接 Student/Hook-model expected-versus-observed 决策；Adapter 在缺少该
  结构时返回 not eligible，而不从 Reviewer prose 推断 Capability。
- Experience Draft 的确认、跨 Attempt/Generation 合并、失效与正式 Researcher 消费未在
  本轮实现。

## 证据位置

- `runs/experiments/20260826_experience_summarizer_redesign_v1/`
- `runs/experiments/20260826_experience_summarizer_redesign_v2/`
- `runs/experiments/20260826_experience_summarizer_redesign_v3_thinking_disabled/`
- `runs/experiments/20260826_experience_summarizer_redesign_v4_budgeted/`
- `runs/experiments/20260826_experience_summarizer_redesign_v5_final_config/`
- `runs/experiments/20260826_researcher_scheme_action_v1/`
