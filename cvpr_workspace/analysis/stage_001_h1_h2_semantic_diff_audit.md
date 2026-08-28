# STAGE-001 H1/H2 语义差异审计

## 审计结论

结论为 **局部实现缺口，不构成需要返回 `cvpr-goal` 的实质语义冲突**。

当前 Controller 已把局部 Trial/Evidence、Hook Feasibility、Mechanism、Compiler、Validation、Conformance、Candidate Review、Promotion 与 Candidate Rejection 串成明确的分层路由；这些路由没有修改 G-001 的 H1/H2 主张，也没有把最终 Candidate accuracy 直接当作职责级 realizability 标签。当前缺口集中在 first-class lineage、typed settlement、冻结 role identity、正式 H1 blind gate 协议和完整 H2 五职责协议。PLAN-001 已分别把这些缺口放在 STAGE-001、STAGE-004 与 STAGE-005 中补齐，因此本任务只建立基线，不提前改变 Reviewer、Gate 或 routing 语义。

本审计和 route matrix 都是 `development_check_only`，不能支持 H1/H2/H3 Claim 或 Goal 验收。

## 真实路由基线

机器可读基线见 `cvpr_workspace/analysis/stage_001_route_coverage_matrix.json`。它覆盖：

- `WorkKind` 的 15 类 durable work；
- `_CompletedTransition` 的 15 个完成处理器；
- 29 个直接 `_one(...)` 调度点；
- 20 个 `TransitionPlan.complete_reason` 终止点；
- Controller 的初始化、失败重试、显式恢复、中断恢复、软预算暂停与 agenda drain；
- Candidate Attempt journal 的 pending、accepted、rejected 结算边界。

路由的上游责任保持分层：Evidence Reviewer 的 `continue` 提供下一证据义务，Evidence Reviewer 的 `revise/reject` 返回 Hypothesis Researcher；Hook Feasibility 的 specification 问题返回 Mechanism Distiller，research 问题返回 Hypothesis Researcher；Compiler 的 evidence、mechanism 与 implementation 问题按来源返回；Conformance 和 Candidate Reviewer 的 evidence、mechanism、implementation obligation 在 Candidate 先持久拒绝后再定向回流。

## 结算 taxonomy 基线

当前代码尚无 first-class settlement schema。以下分类是本任务对真实路由的审计映射，不是已实现的新运行时状态：

| 分类 | 职责 | 当前可定位事实 |
|---|---|---|
| `provisional` | 表示仍需后续 work 或 bounded revision，不能形成跨 generation settled experience。 | `_one(...)` 调度、Candidate revision、Hypothesis revision 与 retry。 |
| `settled_positive` | 表示一个生命周期边界上的耐久正结果。 | Candidate Attempt `accepted`、promotion receipt 与 `version_advanced`。 |
| `settled_negative` | 表示证据、可实现性、实现、评审或局部预算已形成耐久负结果。 | Candidate Attempt `rejected`、`not_distillable`、无匹配 Prefix、各类 path-local budget terminal。 |
| `invalid_indeterminate` | 表示执行或证据有效性不足，不能解释为科研负结果。 | 未恢复 work failure、Controller 软预算暂停、无 typed terminal 的 agenda drain。 |

Candidate 被持久拒绝后可以启动新的 research attempt。因此 `settled_negative` 可以发生在 Candidate Attempt 边界，而不要求整个 Controller Run 同时结束。现有代码没有显式表达这个嵌套结算边界；后续 settled-trajectory contract 必须保留这种区别。

## Lineage 差异

| 字段 | 职责 | 当前状态 |
|---|---|---|
| `generation` | 标识 incumbent/version 演进的一代，并绑定 `version_advanced`。 | 已存在于 Work payload 和 ControlState。 |
| `optimizer_episode_id` | 标识一个可独立结算、可跨 attempt 汇总的 optimizer episode。 | 缺失。 |
| `research_attempt_id` | 稳定标识一个研究方案 attempt，不能仅靠可复用整数推断。 | 缺失；当前只有 `research_attempt` 计数和派生的 problem/solution lineage 字段。 |
| `candidate_attempt_id` | 标识一次持久 Candidate 物化、验证、接受或拒绝生命周期。 | 已由 Candidate Attempt journal first-class 保存。 |
| `source_verdict_ref` | 将结算状态绑定到产生它的 Reviewer/Gate/effect artifact。 | 分散在 `input_refs`、effect artifact 与 payload 中，尚无统一字段。 |

`WorkItem.work_id`、`parent_work_id` 与确定性 `_stable_id` 能重放控制流，但不能替代研究语义上的 episode/attempt lineage。后续合同不应从 work ID 字符串反推这些边界。

## Role identity 差异

`build_role_artifact` 已保存 role ID/version、model provenance、output contract ID/version/schema digest、validated input、resource config、transcript 与 `template_root`。这些字段足以定位一次开发调用，却不足以冻结 G-001 所需的完整 role identity。

| 字段 | 职责 | 当前状态 |
|---|---|---|
| `role_id` / `role_version` | 标识角色职责与代码内注册版本。 | 已存在。 |
| `model` | 标识 Teacher provider/model 与运行参数来源。 | 已存在 provenance。 |
| `output_contract_digest` | 标识输出 schema。 | 已存在 `schema_digest`。 |
| `base_prompt_template_digest` | 冻结 system instructions、user template 与 continuation templates 的内容。 | 缺失；`template_root` 只是可变路径。 |
| `role_contract_digest` | 冻结输入/输出职责合同，而不只冻结输出 schema。 | 缺失。 |
| `input_view_digest` | 冻结本次角色真正可见的 rendered input/resource projection。 | 缺失。 |

因此现有 role artifact 不应直接作为跨 generation experience scope 的完整 identity key。

## H1 语义核对

一致部分：

- Trial 在 Candidate 编译前运行，Trial artifact 与 Evidence Review 先于 Mechanism Distillation 和 Compiler。
- `ready_to_distill`、`needs_evidence`、`not_distillable` 与 Compiler/Conformance 路由保持研究证据、机制和实现层分离。
- Candidate Review 后还有 deterministic safety/effect promotion gate，Reviewer 推荐不能单独覆盖验证、执行错误、accuracy safety 或 effect-goal 约束。
- Trial、Reviewer、Compiler、Conformance 与 Candidate artifacts 都能通过 journal/effect refs 定位，Goal 前历史 Run 仍被排除。

局部缺口：

- H1 的 repeated matched no-op/intervention 双臂、冻结 Prefix/Trial selector、frozen Gate decision、Gate 后 blind compilation 与 rejected bypass audit 尚未实现；这与 PLAN-001 STAGE-004 的既定补齐范围一致。
- Evidence Reviewer 的 `reject` 当前与 `revise` 一样进入 bounded Hypothesis revision；它还不是可直接冻结、进入 blind downstream audit 的 typed Gate rejection artifact。
- `complete_reason` 只保存自然语言，不携带可机器连接的 verdict ID、obligation owner、settlement class 或 source artifact。

这些缺口意味着当前开发流程不能执行 EVAL-H1，但没有把 H1 的核心 Gate 含义改成别的研究主张。

## H2 语义核对

一致部分：

- Hook Feasibility 在 Candidate compilation 前运行，并基于真实 Prefix/phase probe 形成 `feasible`、`needs_spec_revision` 或 `needs_research_revision`。
- specification 问题返回 Mechanism Distiller，research 问题返回 Hypothesis Researcher；feasible guidance 只进入 Compiler constraints。
- Candidate Conformance 独立检查实际实现，并把 evidence、mechanism、implementation 三类修复义务返回对应上游。
- 最终 Candidate accuracy 没有替代 Hook Feasibility 或 Conformance 的局部职责判断。

局部缺口：

- 当前 Hook Feasibility 仍是 phase-oriented feasibility，尚未完整表达 G-001 锁定的 recognition、decision、adherence、fallback、parse 五职责 prediction 与独立 shadow/in-loop label。
- no-feasibility-routing、always-Student、always-deterministic 与 adaptive routing 四条件尚无冻结 condition identity 和公平 control adapter。
- 当前 phase result 与 downstream Candidate outcome 之间没有 first-class responsibility-level joined receipt。

这些缺口意味着当前开发流程不能执行 EVAL-H2A/EVAL-H2B，但没有用 aggregate Candidate utility 替代职责级主张。

## Replay、retry 与结算风险

- Control journal 使用连续 sequence、append-only JSONL，并在 append 前完整 replay；相同 `work_id` 只能以相同内容重复调度。
- Effect artifact 采用临时文件加 `os.replace` 原子写入；中断后存在 effect 就恢复为 completed，不存在就记录 failed。
- Work retry 使用父 work ID、attempt 与 kind 生成新的确定性 ID，不覆盖原 work。
- Candidate promotion/rejection effect 会先查询已完成 receipt，避免 retry 重复接受或拒绝同一 Candidate Attempt。
- 当前 Controller 的显式 resume 允许为已经因 retry exhausted 而暂停的 work 再建一个新 attempt。这是人工恢复入口，不重复旧 work，但后续 settled contract 必须明确它是 recovery attempt，而不是同一 terminal 的第二次结算。

## Budget 语义边界

Trial、assignment、Hypothesis、Mechanism、Compiler、Candidate revision 与 generation budget 已有明确路由。Controller 的 work-item/token budget 仍是 effect 启动前的 soft pause，`ControlState` 只聚合 `total_tokens`；它不是 G-001 要求的 all-in reservation/commit/refund。该缺口属于 PLAN-001 STAGE-005，不在本任务中修改。

## 后续 STAGE-001 输入

后续实现应以本 matrix 为稳定基线，新增 first-class episode/attempt lineage、typed settlement、route-to-obligation schema 和冻结 role identity。新增合同必须保持现有 H1/H2 Reviewer decision 与责任路由，不得把开发检查解释成正式 Gate、职责预测或 Candidate utility 证据。

