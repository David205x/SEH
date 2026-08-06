# Evolution Runner

## 职责边界

`search_harness.evolution` 负责把已有 Actor rollout、evaluation、Critic、Intervention
Coordinator、Compiler 与 Harness Version Store 串成单候选、线性的离线进化流程。

系统硬边界与语义验收分离：

- Version Store validator 强制检查 manifest、fixed 组件边界、import 与 Python 语法。
- Critic candidate review 输出 `review.decision=accept|reject` 和理由，是候选是否进入版本库的语义决策源。
- 证据不足时 Critic 应拒绝候选，并在 reason 中说明缺失证据。

## 单轮流程

1. 在固定 Experience Set 上评估最新 accepted Harness。
2. Critic 进行 failure analysis，输出行为级问题方向，并读取失败尝试摘要。
3. Coordinator 对最高优先级问题方向执行跨案例 Intervention；只有 `supported` 继续。
4. Compiler 将验证后的策略编译为一个原子 patch transaction。
5. Version Store 对候选执行 deterministic validation。
6. 在同一 Experience Set 上 rollout 和 evaluate 候选。
7. Critic 以候选为 primary、父版本为 comparison 进行对比评审。
8. Runner 根据结构化 review 接受或拒绝 Version Store iteration。

Compiler 返回 `clarification` 时不会立即结束 run。Runner 先拒绝该空候选事务，再将
Compiler 的原始反馈、上一版 Coordinator trial ledger 和同一 Critic 问题方向送回
Coordinator。Coordinator 使用新的 Worker trial 预算补测缺失的通用行为，随后再次调用
Compiler。该内层修订默认最多执行 2 次，可通过 `--compiler-revision-limit` 设置；只有
预算耗尽仍无法编译时，run 才以 `needs_clarification` 结束。一次澄清 attempt 不计作
外层 iteration 决定，也不会进入后续 failure memory。

Coordinator 首次返回 `inconclusive` 时也不会立即结束 run。Runner 会将上一轮完整 trial
ledger、分析与 recommendation 交给新的 Coordinator 会话，分配一份新的 Worker trial
预算，要求实际执行尚未完成的通用机制实验并补齐跨案例证据。默认最多续验 2 次，可通过
`--intervention-continuation-limit` 设置；每次续验拥有独立的
`--intervention-max-trials` 预算。`rejected` 表示方向已被证据否定，不触发续验；只有连续
`inconclusive` 耗尽续验次数后，run 才以 `no_supported_strategy` 结束。

Compiler patch 未通过 deterministic validation 时也不会立刻消耗一个外层 iteration。
Evolution backend 会拒绝无效 Version Store transaction，把完整校验报告和上一份 Compiler
结果反馈给一次新的 Compiler 会话，并要求相对同一 accepted parent 返回完整替换事务。
默认允许 4 次校验返修，可通过 `--compiler-validation-repair-limit` 调整。所有尝试均写入
最终 Compiler log 的 `attempts`，无效事务保留在 Version Store journal 中并标为 rejected。

Compiler 的最终结果属于角色运行时协议，不由可进化插件决定。固定的 `PRE_FINAL` 守卫会
严格解析 final-answer 内的 `summary/edits/clarification` JSON；Markdown fence、非法转义、
缺失字段或不合法 edit 会被转成模型可见反馈，在同一 Compiler 对话中修正。若错误发生在
最后一步或仍逃逸出 AgentLoop，backend 会先保存完整 run、raw answer 与错误，拒绝对应
Version Store transaction，再在原始 parent 上启动新的 Compiler 会话。协议修复与静态
校验修复共享 `--compiler-validation-repair-limit`，因此不会产生无限重试或遗留 pending
workspace。

静态 validation 通过后，Evolution backend 还会从冻结 Experience Set 按模型 seed 与
candidate digest 可复现抽取样本，使用真实 Actor 模型、工具和候选 Hook 执行 smoke
rollout。默认抽取 1 条，可通过 `--compiler-smoke-examples` 调整。任何 Hook phase 异常、
runner error 或未完成状态都会拒绝当前 transaction，并连同完整 smoke trace 反馈给新的
Compiler 会话；只有 smoke 通过后才运行完整 candidate evaluation。新增或修改的 Python
文件还会接受 AST 规则审查，禁止用 `getattr`、`hasattr`、`setattr`、`delattr` 掩盖未知
环境接口。

拒绝尝试不会生成 Git 版本，但其候选摘要、指标、validation 报告与拒绝理由会保留在
`events.jsonl`，并作为有界失败记忆进入后续 failure analysis。重复出现的已拒绝 candidate
digest 会在再次 rollout 前被拒绝。同一 accepted parent 在候选连续被拒时复用本 run 内
已经完成的 incumbent rollout/evaluation，不重复消费 Actor 与 Judge 调用。

## Memory 边界

当前没有所有角色共享、自动检索的跨迭代长期 memory。一次 `AgentLoop` 内的消息只在该次
角色运行中延续；Coordinator artifact 持久化本次 trial ledger，并仅在 Compiler
clarification 修订时显式继承；Runner 向下一轮 Critic 传入有界的失败尝试摘要；accepted
Harness 则保存已经固化的行为。`events.jsonl` 是恢复与审计事实来源，不会自动进入模型
上下文。

## 结构化结果与缺失值

Adapter 角色的结构化结果使用同一组边界规则：

- schema 必填字段必须显式出现；不得由 parser 静默补空数组、空字符串或 `null`。
- 只有 schema 明确允许为空的值才能使用空值，例如 failure analysis 的 `review: null`。
- 缺字段、未知字段、错误类型和空的必填字符串都属于生产者协议错误。
- 固定 `PRE_FINAL` guard 在角色对话内返回精确错误并要求重写完整结果。
- 若 guard 在最后一步无法完成修复，Evolution backend 使用有界的新会话重试。
- 已持久化但不符合当前 schema 的 Critic artifact 会被追加
  `failure_critic_invalidated` 事件并重新生成；下游仍保持 fail-fast，不猜测缺失语义。

Critic、Coordinator 与 Compiler 共同复用一份 `problem_direction` 校验器，六个必填字段为
`problem`、`observed_pattern`、`excluded_causes`、`desired_behavior`、
`success_criteria` 和 `constraints`。这保证生产、实验和编译阶段不会使用不同严格度解释
同一份证据。

## 持久化与恢复

每个 run 目录包含：

```text
run.json
events.jsonl
experience_set.jsonl
iterations/0001/
  incumbent_rollouts.jsonl
  incumbent_report/
  failure_critic.json
  intervention/
    coordinator/<run_id>/coordinator.json
    trials/<run_id>/intervention.json
  intervention_continuation_01/
    coordinator/<run_id>/coordinator.json
    trials/<run_id>/intervention.json
  compiler.json
  intervention_revision_01/
    coordinator/<run_id>/coordinator.json
    trials/<run_id>/intervention.json
  compiler_revision_01.json
  candidate_rollouts.jsonl
  candidate_report/
  candidate_review.json
  decision.json
```

`events.jsonl` 是 UTF-8 append-only 状态日志。恢复时以已提交事件跳过完成阶段；若 Version Store 已经 accept/reject、Runner 尚未写入对应事件，Runner 会先对账并补记决定。已持久化的 `candidate_reviewed` 不会再次调用 Critic。

## CLI

启动新 run：

```powershell
python -m search_harness.evolution run `
  --run-dir runs\experiments\evolution\run_001 `
  --checkpoint-store harness_checkpoints\search_actor `
  --limit 20 `
  --max-iterations 3 `
  --critic-protocol-repair-limit 2 `
  --intervention-continuation-limit 2 `
  --intervention-max-trials 10 `
  --compiler-revision-limit 2 `
  --compiler-validation-repair-limit 4 `
  --compiler-smoke-examples 1 `
  --rollout-workers 2 `
  --rollouts-per-example 3 `
  --judge-workers 8
```

恢复中断 run：

```powershell
python -m search_harness.evolution resume runs\experiments\evolution\run_001
```

新 run 会把 dataset、模型角色、插件路径、步数限制和 Experience Set digest 写入 `run.json`。恢复默认复用这些记录，也允许通过 CLI 显式覆盖 backend 参数。当前 paired evidence 只强制对齐复合样本身份和 sampling seed，不会拒绝模型 ID、temperature、endpoint 或插件配置变化；因此语义实验不应在已有 run 的恢复过程中覆盖这些参数或修改 `.env`。仅日志级别、worker 数等不改变样本语义的运行设置适合恢复时调整。

Actor 样本以有界线程池并发执行，默认 `--rollout-workers 2`；每条 rollout 使用独立
Loop、模型客户端、工具和 Hook 实例。Teacher 只并发裁判静态规则无法确定的样本，默认
`--judge-workers 8`，每个线程持有独立 Judge/模型实例。两类结果均按 Experience Set
原始顺序和 replicate 顺序写入。`--rollouts-per-example` 默认 1，并对 incumbent 与
candidate 使用相同次数和 seed schedule；该值与 worker 数写入 `run.json`，恢复时默认沿用。

## 运行进度与日志

CLI 默认以 `INFO` 级别输出每轮的阶段开始、完成、耗时、主要指标、artifact 路径和最终 accept/reject 决定。Actor rollout 与 evaluation 继续使用 `tqdm` 显示样本级进度；阶段日志通过 `tqdm.write` 输出，不会破坏动态进度条。

同样的可读日志会以 UTF-8 追加到：

```text
<run_dir>/evolution.log
```

`events.jsonl` 仍是状态恢复的事实来源，`evolution.log` 只用于人工观察。恢复执行时，CLI 会明确显示被复用的 evaluation、Critic、Compiler 或 review artifact。

可以通过 `--log-level DEBUG|INFO|WARNING|ERROR` 控制日志级别。`--no-progress` 只关闭 `tqdm` 动态进度条，不会关闭关键阶段日志。
