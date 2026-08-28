# TASK-007 Prompt 角色驱动 Sub-agent 审查

## 1. 编排信息

- 模式：`cvpr-someagents` 模式 B，多角色分析。
- 输入快照：当前 Experience Summarizer Prompt/Input/Contract、`TASK-007_plan_v11.md`、类型提取审计、18-case fixture、v1/v2 真实 API 输出、角色职责和 Transition 实现。
- 独立性：三位 sub-agent 并行执行，互不读取彼此结论，均为只读。
- `/root/task007_summarizer_role_validation`：Experience Summarizer 执行者。
- `/root/task007_consumer_role_validation`：下游 Experience consumer。
- `/root/task007_attribution_reviewer_validation`：Attribution Reviewer / Prompt 红队。
- 原始输出：`TASK-007_prompt_role_driven_review_raw_v1.md`。

## 2. 各角色结论

### 2.1 Summarizer 执行者：`conditional_pass`

v11 的“结论对象优先”、固定 lesson 组成和独立第二条规则是正确主干，但还缺少：

- no-differential、clean falsifier、harmful over-trigger 对 capability 的覆盖优先级；
- properly formed but falsified hypothesis 与 Teacher work defect 的边界；
- capability 所需有效正例机会数和重复条件；
- route target repair 不能作为 Teacher fault 证据；
- 第二条经验的独立事实定义；
- `attempt` 与 `boundary` 冲突时以哪一个为权威。

### 2.2 下游消费者：`conditional_pass`

v11 能形成基本 consumer-ready Draft，但还需要把消费者动作写进 lesson：

- capability：不得依赖、增加 deterministic guard，或满足什么 recheck 才能解除；
- teacher work：下一步动作和可检查完成标准；
- direction：方向签名、停止/缩窄/inconclusive/conditional-continue disposition，以及合法重访条件。

同一事实和同一未来动作即为重复，即使换成不同 Experience Type 也不能并存。本任务只能验收 consumer-ready Draft，不能声称已经减少跨 Run recurrence 或 direction duplication。

### 2.3 Attribution Reviewer：`fail`

Reviewer 发现五项阻断：

1. 真实 Transition route 与 fixture 中的 `route_target_role` 不一致。
2. “替换 Teacher 后是否仍成立”无法区分 Teacher work 与 direction，因为 Role Contract 义务也跨 Teacher 实例成立。
3. 计划输入不能证明 Teacher 作出决定时已经看见完成职责所需事实。
4. 缺少 invalid/indeterminate 的确定性 eligibility gate。
5. 20 次应是绝对熔断，不是鼓励使用的语义预算；现有架构文档也需要同步。

## 3. 独立核对的关键事实

`candidate_validation_query_coverage_defect` 的 source artifact 状态是 `unchanged_rejected_candidate`，且 `prior_validation.passed=true`。Controller 对该状态调用 `_new_research_attempt()`，没有回到 Compiler。当前 fixture 却写 `candidate_validation.rejected -> compiler`，因此把 causal Compiler subject 冒充成真实 route target。

普通 `validation_failed` 只有在 Compiler revision budget 未耗尽时才回 Compiler；预算耗尽时 terminal。由此可见 trigger 不能无条件映射固定 route target，必须从实际提交的 TransitionPlan 投影真实 route。

## 4. 综合裁决

综合结论为 `fail`，不采用 2:1 多数覆盖红队阻断。v11 不应直接实施。

下一版必须同时解决：

- typed source eligibility；
- exact decision/Transition context；
- route target 与 causal Teacher subject 分离；
- Teacher 当时 input sufficiency 的权威证据；
- 三类 Experience 的严格顺序、consumer action 和解除/重访条件；
- fixture 的真实 source/route 修正；
- 20-call hard fuse 与正常 0–3 次工具使用的区别。
