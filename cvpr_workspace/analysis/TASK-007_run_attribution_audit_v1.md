# TASK-007 历史 Run 负向决策归因审计

## 审计边界

本审计只用于确定 Experience Summarizer MVP 需要看到哪些输入，不把历史 Run 作为 H3 方法效果或 Goal 验收证据。

审计范围：

- `runs/evolution/20260815_qwen3-8b_hook_feasibility/`
- `runs/evolution/20260806_qwen3-8b/`
- `runs/evolution/20260803/`

## 案例观察

### Evidence Reviewer revise

- 决策 Work：`runs/evolution/20260815_qwen3-8b_hook_feasibility/artifacts/review_evidence-054cca1b11f4a49c/`
- Reviewer 观察到第二实体检索在部分 Trial 中没有返回目标事实，因此要求修订 success condition。
- 上游 Hypothesis 已记录 corpus sufficiency 未验证，但 success condition 仍要求 revised answer 引用第二实体证据。
- 只看 Reviewer 决策可以知道“需要修订”，但不能区分问题来自 Reviewer、上游成功条件还是语料不可检索。
- 最小补充内容是上游 Hypothesis 的 success condition/known limitation，以及失败 Trial 的 follow-up query、目标事实是否出现、revised final 与 score；完整 transcript、Model Input 和 Tool Call 不需要。

### Hook Feasibility needs_research_revision

- 决策 Work：`runs/evolution/20260815_qwen3-8b_hook_feasibility/artifacts/verify_hook_feasibility-64ddfe9a2a85e492/`
- 负向结论来自同一 case 在 enabled repetition 中翻转，以及 disabled mode 对 negative cases 的误报。
- 仅看最终 assessment 可以形成初步 Student capability 结论，但要区分 evaluator contract 歧义和 Student-profile 稳定性，需要对照冻结 contract 与 expected × thinking mode × repetition label matrix。
- 不需要完整 probe prompt、conversation、passages、reasoning、usage 或 experiment hash。

### Conformance revise_implementation

- 决策 Work：`runs/evolution/20260806_qwen3-8b/artifacts/verify_conformance-112c1011c5657e1c/`
- Conformance finding 指出预期 activation budget 为 4，但 Candidate 继续 defer。
- 当前 summary 已接近足够；只需交叉核对 Compiler 关于“由 runtime phase activation budget 执行”的实现声明，以及一条包含 defer 次数的 finding。
- 不需要 Candidate replay、finding transcript 或完整 Compiler Artifact。

### Candidate Reviewer reject

- 决策 Work：`runs/evolution/20260806_qwen3-8b/artifacts/review_candidate-9c4407ec7edef219/`
- Candidate 已通过 validation/conformance，但 Mechanism 的单 passage explicit-relation predicate 导致正确答案被反复 defer，成本约束与稳定性恶化。
- Reviewer output 已给出较强归因，但形成可复用方向经验时仍需对照 Mechanism relevant rule 和少量 regression causal slice，才能确认问题属于机制条件而非 Compiler 实现。
- 最小对照是 aggregate delta 与至多三条 regression/improvement 切片；不需要完整 225-rollout 文件、全部 passages 或 Hook transcript。

## 对 MVP 输入的结论

- 决策点 compact view 适合作为默认输入，但不能被当作完整根因。
- `responsible_role` 应改为 `route_target_role`：它只是 Controller 已提交的下一修正角色提示，不是已确认责任归因。
- Initial Input 仍保持五字段；上游/过程证据通过受限工具按需获取，不固定注入完整因果链。
- Prompt 在产出经验前应检查：当前决策执行、上游 contract/实验设计、implementation、数据或环境充分性四个责任层。

## 最小按需工具

`inspect_experience_evidence(evidence_ref, view, selectors=[])`

- `evidence_ref` 只能从本次 Summary Input 已授权的 evidence key 中选择，禁止传入路径。
- `view` 只允许 `upstream_contract`、`decision_trace`、`candidate_comparison`。
- `selectors` 只能使用初始 observation 暴露的 case/finding/example ID，最多三个。
- 一次返回最多三条、单条不超过 1500 字符、总计不超过 4000 字符；一次总结最多调用两次。
- passage 仅返回与判因直接相关的至多两个摘录，每个不超过 400 字符。
- 永久排除完整 Prompt、transcript、conversation、Model Input、raw reasoning、resource config、完整 rollout/report、workspace/code 和 hash/digest。

## 后续观察项

- 统计 Summarizer 的工具调用率、工具后归因改变率、空输出率；高频必需的上游视图再考虑固定进入 Initial Input。
- 若实验显示 route target 经常不是经验责任角色，再讨论是否引入独立 attribution target；MVP 不新增该字段。
- 读取目标角色已有 experience，并判定 duplicate、revise 或 new，留到 Store/检索接入任务。
