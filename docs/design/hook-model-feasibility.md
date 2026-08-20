# Hook-model Feasibility

状态：已实现，默认对新 Run 启用；旧 Run 缺少开关时保持关闭。

## 目标

Intervention Trial 证明 Teacher 已知触发位置时的干预效果，不证明 Student 能在 Candidate
运行时独立识别相同语义边界。Hook-model Feasibility 在 Mechanism Distiller 与 Compiler
之间补充后一项证据，避免 Compiler 通过多轮 Conformance 失败才开始探索模型能力。

## 实现边界

- Controller 仅在 `hook_feasibility_enabled=true` 且 Mechanism 至少有一个
  `decision_evaluator=hook_model` phase 时调度 `verify_hook_feasibility`。
- Probe 从 Distiller 输入中的 Trial Review 取得 reference label，并恢复同一 Trial 的原始
  prefix；调用 Student 作三值判断后立即结束，不修改上下文、不继续 Student 轨迹。
- 每个 phase 使用同一冻结 decision contract，按配置比较 thinking mode 和重复调用。
- 程序保存完整请求、原始输出与 usage，只做描述性计数；Hook Feasibility Reviewer 负责
  语义忠实性、稳定性、成本与路由判断。
- `feasible` 将真实 prefix experiment 与 thinking/parser 指导交给 Compiler；模型边界、
  支持范围或研究覆盖失败回到 Researcher；仅操作定义或 runtime input 歧义回 Distiller。

## 回退

将 `evolution.effects.hook_feasibility_enabled` 设为 `false` 后，新建 Run 会恢复
`distill_mechanism → compile_candidate` 路由。Run 创建时会把该值冻结到 `run.json`；因此
关闭全局配置不会改变已经创建的 Run，旧 Run 也不会因代码升级自动插入新阶段。

## 验收

1. deterministic-only Mechanism 跳过该阶段。
2. Hook-model Mechanism 在 Compiler 前产生 `probe.json` 和 Reviewer artifact。
3. Probe 请求不含 reference label，且没有分支 Student continuation。
4. Reviewer 的可行结论把真实 experiment 与实现指导传给 Compiler。
5. 语义能力失败通过 Researcher continuation 修订 Hypothesis。

## 真实 Artifact 验证（2026-08-15）

以 `20260815_qwen3-8b_fullchain_fix` 的 Distiller、Trial Review 与 Incumbent
rollout 为输入，Probe 恢复 4 个真实 `pre_final` prefix，比较 Student Hook-model 的
thinking enabled/disabled，各重复 2 次，共 16 次调用、31,140 token。enabled 在 4 个
边界中稳定复现 3 个，disabled 稳定复现 2 个；没有任何模式覆盖完整边界，因此不应把
该方案交给 Compiler。

Reviewer 使用紧凑投影后，3 次 thinking-enabled 审查均返回
`needs_research_revision`，并一致把失败归因到 Hook 输入不可观察的实体身份边界；token
分别为 111,203、53,942、52,795。关闭 Reviewer thinking 的成功调用更便宜，但 3 次中
2 次错读 t002 的 reference label，另一次独立尝试耗尽 12 回合，因此正式配置保留
thinking enabled。该实验说明本阶段能在 Compiler 前识别模型能力边界，也说明 Teacher
结构化提交的长尾重试仍需由通用 Role Runner 单独治理。

## 完整 Evolution 验证（2026-08-15）

新建 `20260815_qwen3-8b_hook_feasibility`，复用既有 75 题 Incumbent Evaluation，使用
独立 Version Store，并冻结 `max_work_items=60`、`max_total_tokens=7,000,000`。第一次
Distiller 后，feasibility 在 4 个真实 prefix 上发现 enabled 模式仅复现 3/4 边界，直接
回到 Researcher，没有调用 Compiler。Researcher 收窄范围并补证后，第二次 feasibility
在同一规模的真实 prefix 上达到 enabled 4/4、每项 2/2 稳定，随后一次 Compiler 和一次
Conformance 即进入 Candidate Evaluation；没有发生 Compiler/Conformance 修订循环。

第一个 Candidate 的准确率为 0.6533（基线 0.6711），token 为 855,992（基线
579,635），其中 Hook 占 429,935。Candidate Reviewer 发现 14 次 positive/上下文改动
没有覆盖目标正例，反而在契约负例产生回归，故 `reject`。这说明真实 prefix
feasibility 能证明已研究边界可实现，但少量研究 prefix 不能替代全分布 Candidate
Evaluation。

第二个研究方向也一次通过 feasibility、Compiler 与 Conformance；但 Compiler 单次消耗
1,401,453 token，表明该阶段只减少语义能力探索的重复尝试，不降低 Compiler 自身的长
上下文成本。第二个 Candidate 准确率 0.6311，相对基线下降 0.0400，低于晋升门
`-0.02`；总 token 1,338,154，其中 Hook 占 931,455。215 次 Hook-model 输出中仅 7 次
positive 并实际改动，另有 7 次非协议 `false` 与 1 次 `uncertain`。Run 在 Candidate
Evaluation 后以 55 个 WorkItem、7,900,897 token 暂停，未启动第二次 Candidate
Reviewer，accepted version 仍为 `harness_v0001`。

`max_total_tokens` 是 WorkItem 边界上的软上限：启动第二次 Candidate Evaluation 前累计
为 6,562,743，单项完成后才超过 7,000,000；Controller 随后暂停。若需要严格不越界，
必须另行设计单项成本预留或可中断预算，本实现不声称提供硬 token 上限。
