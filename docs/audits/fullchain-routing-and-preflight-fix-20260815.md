# Full-chain Routing and Preflight Fix（2026-08-15）

本轮只修正当前链路中的研究、证据义务、Compiler 接续与 Conformance 预检；不实现经验系统，也不改变 Student Template 或既有角色的研究目标。

## 已实施内容

1. Hypothesis Researcher 在冻结一个假设前，内部比较至少两种实质不同的介入策略，再把选定策略写成 phase、可观察触发、动作、即时效果和 falsifier；输出协议未增加字段。
2. Evidence Reviewer 输入新增 Trial Selector 权威能力边界。Selector 只能定位冻结 phase 的未使用 prefix 并优先扩展 Example/replicate，不能按未来 Student 行为或语义标签选样；不可履约的随机 outcome 不得再成为 `continue` obligation。
3. Student Model Experiment 增加稳定签名与跨 Compiler revision 复用。底层 artifact 保留完整 prompt、case、逐次 raw output、usage 与 metadata；工具结果仅按 case/mode 聚合输出和总 token。Compiler 通常使用相同 case 对 thinking enabled/disabled 配对比较，不以低成本本身替代边界质量判断。
4. Compiler implementation revision 仍新建 Role Session，但继承上一轮 workspace、changed files、API query 记录和模型实验；新输入 `conformance_failures` 直接提供非 faithful finding 的失败层、期望/实际标签、决定性输入摘要与修复义务。continued workspace 未发生任何改变时，`finalize_candidate` 返回 `repair_required`，不允许原样重交。
5. Conformance 在少量 Candidate replay 后使用与正式 Evaluation 相同的 static evaluator 和 Teacher Judge 生成 score/assessment；Reviewer 分别输出实现保真与 `local_efficacy`。明确 harmful 且实现保真时在完整 Candidate Evaluation 前回到 evidence；若存在实现 mismatch，则 implementation repair 优先。neutral/inconclusive 不被伪装成收益。

## 真实 API 验证

### Evidence Selector 边界

使用 `20260815_qwen3-8b_fullchain` 中曾要求“继续运行直到出现 post-deferral failure”的 `review_evidence-e44a22404ef03e65` 输入并行重跑 3 次。结果为 3/3 `revise`、0/3 `continue`：三次均明确说明该未来 Student outcome 不能由当前 Selector 保证，应保留 4/4 已支持的即时检索效果并删除或改写 persistence obligation。总 token 分别为 37,557、17,468、17,761。

Artifact：`runs/components/role_regression_20260815/evidence_selector_boundary/`。

### Researcher 策略探索

使用同一历史 Failure Direction 并行重跑 3 次。三次都提交单一、可执行且保持边界的 Hypothesis：两次选择 corrective `pre_final` deferral，一次选择 preventive `post_tool` guidance，并为 preventive 方案显式增加自然恢复/不必要介入义务。结果表明新指导能产生介入策略层面的差异，而不是只改写同一提示文本；同时也说明策略选择本身仍有模型方差，后续 Evidence 必须继续约束其范围。总 token 为 44,852、86,572、53,941。

Artifact：`runs/components/role_regression_20260815/researcher_strategy/`。

### Compiler continuation

以旧 digest `bc7ecfd…` 的被拒 Candidate、对应 Conformance failures 和同一 Mechanism 并行重跑 Compiler 3 次。三次均实际调用 `write_candidate_file`，提交相同新 digest `232f2922…`，没有出现无修改提交；每次只运行一个边界实验并选择 thinking enabled，随后修正 evaluator 的 query-names-second-entity negative 边界。Compiler token 为 212,969、304,815、274,408。

Artifact：`runs/components/role_regression_20260815/compiler_continuation/`。

### Candidate Conformance 与局部效果预检

对旧、新 Candidate 分别使用 4 个历史 Trial Example、每题 3 个真实 Student replay：

| Candidate | Conformance | Findings | Local efficacy |
| --- | --- | --- | --- |
| 旧 `bc7ecfd…` | revise | 5 evaluator mismatch，7 faithful | 2 harmful，10 neutral；修正后的聚合优先路由 implementation |
| 新 `232f2922…` | pass | 12 faithful | 12 neutral；gate 为 inconclusive |

新实现的保真改善得到同一套真实 replay 支持。局部预检也暴露出边界：新一批 replay 全部自然走正确不触发分支，因此它只能确认没有观察到局部伤害，不能证明任务收益；完整 Candidate Evaluation 仍然必要。这个结果符合“预检只做负向拦截、不用小样本晋升”的设计。

Artifact：`runs/components/role_regression_20260815/prior_conformance/` 与 `runs/components/role_regression_20260815/compiler_conformance/`。

## Compiler Session 结论

Compiler revision 当前不是继续同一对话 transcript，而是新开 Role Session。这样避免把前一轮长工具轨迹和实验输出无限带入上下文；重复阅读通过继承 workspace 的完整 changed files、`queried_symbols`、模型实验和结构化 Conformance failures 来减少。真实复测中三个新 Session 都只读取现有 extension 后做一次局部写入，说明“新会话 + 结构化接续”已经能够减少重复实现探索，同时保留失败隔离和独立审计。
