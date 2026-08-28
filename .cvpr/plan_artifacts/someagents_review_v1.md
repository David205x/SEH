# PLAN-001 多 Agent 审查记录

审查模式：`cvpr-someagents` 模式 B。三位独立 Agent 接收相同的 `PLAN-DRAFT-v1`、IDEA-001R3、G-001、development base 和代码事实，只使用不同审查角色。初审均为 `revise`；协调者形成 `PLAN-DRAFT-v2` 后，三位 Agent 分别复核其原始阻断问题，最终均为 `pass`。

## 共同输入版本

- IDEA：`.cvpr/start.yaml` 中 accepted IDEA-001R3。
- Goal：`.cvpr/goal.yaml` 中 accepted G-001。
- Development base：`main@72754289913aa0c251aeb559b8ee698862f56150`。
- 用户边界：现有实验全部排除；H3 为当前主要实现对象；H1/H2 保持机制语义稳定，但必须补齐 Goal 已锁定的正式协议；H3 完成后只在非 held-out 上联合开发验证，最终冻结后从零取证。
- 初审输入：九阶段 `PLAN-DRAFT-v1`。
- 复核输入：十阶段 `PLAN-DRAFT-v2`，对应最终 `PLAN-001 v1`。

## Code review

- Agent：`/root/plan_code_review`
- Role：`code_consistency_and_engineering`
- 初审：`revise`
- 初审主要阻断：H3 不能是隐式 Store 副作用；settled cycle 和 role identity 不完整；untyped `historical_experience` 可绕过 scope；usage/effect receipt 时序混淆；H1/H2 正式协议和 controls 未实现；soft token pre-check 不满足 hard all-in budget。
- 修订：STAGE-001–005 分别补入稳定 terminal taxonomy、first-class experience lifecycle、typed scoped projection、H1/H2 protocol completion 和 Controller-level hard budget/conformance freeze。
- 复核：`pass`，无剩余阻断。

## Science review

- Agent：`/root/plan_science_review`
- Role：`scientific_path_and_goal_coverage`
- 初审：`revise`
- 初审主要阻断：reject-only 经验会使 direction map 缺少正向 outcome；memory controls 不完整；H1/H2 正式核验未明确关闭 H3；AC-SAFETY-UTILITY 的组成证据和最终判断边界不清。
- 修订：STAGE-002 覆盖全部 settled 正负终态；STAGE-003 实现全部 required controls；STAGE-007 使用空 Store；STAGE-007/008/009 分别形成 safety 组成证据，STAGE-010 联合审计。
- 复核：`pass`，全部 required AC 获得实现、formal verification 和 evidence audit 覆盖。

## Validity review

- Agent：`/root/plan_validity_review`
- Role：`experimental_validity_and_real_verification`
- 初审：`revise`
- 初审主要阻断：result freeze 与 protocol freeze 混淆；统计计划和标签操作定义不完整；bypass 没有已知选择概率和设计一致估计；H3 Store 可能被跨阶段预灌；held-out controls 可能事后选择。
- 修订：STAGE-005 先冻结 result-candidate 和 protocol skeleton；STAGE-006 再通过隔离 calibration 冻结完整 preregistration；旁路使用非零概率、概率日志和加权估计；H3 各条件使用独立冷 Store；held-out 使用 deterministic advancement/control-selection。
- 复核：`pass`，无剩余阻断。

## 协调结论

最终结论：`pass`。

所有初审阻断均已进入 PLAN-001 的阶段范围、验收规则、阻断条件或 evidence artifacts。一个审查建议曾把 STAGE-010 evidence audit 放入 `verification_stage_ids`；协调者保留其“最终联合判定”实质，但按 Plan Schema 将 STAGE-007/008/009 作为真实 verification stages，STAGE-010 作为独立 evidence audit，不将审计节点错误标记为真实验证节点。
