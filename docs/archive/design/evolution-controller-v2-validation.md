# Evolution Controller v2 闭环验证

## 结论

2026-07-29 的本地真实运行已验证 v2 Controller 能把七个 Teacher 角色、
Actor 配对评估和 Version Store 串成可恢复闭环。

验证得到的终态是“拒绝候选并保留 incumbent”，不是 promotion：

- 30 个冻结样本，每题 2 次 rollout，共 60 条 incumbent 和每候选 60 条
  rollout；
- 先后创建、校验和评估 2 个 pending candidate；
- 第一个候选由 Candidate Reviewer 要求修订，Controller 先拒绝 pending
  iteration，再返回机制层；
- 第二个候选虽然得到 Reviewer 的 `accept` 建议，但 accuracy 从 `0.80`
  降到 `0.75`，确定性 promotion gate 拒绝晋升；
- 两个 iteration 最终均为 rejected，Version Store 没有遗留 pending
  candidate，accepted version 仍为 `harness_v0001`。

这说明闭环控制面可以完成“研究、试验、蒸馏、编译、校验、全量候选评估、
评审、修订和拒绝”路径，并能在模型建议与确定性门禁冲突时保持版本安全。

## 环境与冻结配置

| 项目 | 配置 |
| --- | --- |
| 操作系统 | Windows |
| Python | `D:\ProgramData\miniconda3\envs\env_search_harness\python.exe` |
| Teacher | `deepseek-v4-flash`，temperature `0.2`，seed `42` |
| Student | `qwen3:8b`，temperature `0.65`，seed `42` |
| 数据 | filtered HotpotQA，固定源文件顺序 |
| Actor 并发 | 3 |
| Teacher judge 并发 | 8 |
| 候选门禁 | 最低 accuracy delta `0.0`，最高 token ratio `3.0` |
| checkpoint | 隔离实验 store `controller_v2_real_01` |

实验使用独立 checkpoint，未修改正式 checkpoint。

主要证据目录：

- `runs/experiments/evolution_controller_v2/real_closed_loop_20260729_01/`
- `controller_run/events.jsonl`
- `controller_run_broad_pool/events.jsonl`
- `checkpoint/.harness-store/iterations.jsonl`
- `checkpoint/.harness-store/versions.jsonl`

## 定向自动化测试

最终定向回归共 88 项：

| 测试组 | 数量 | 结果 |
| --- | ---: | --- |
| Controller 与 intervention prefix | 13 | 通过 |
| Teacher contracts/runtime/resources | 62 | 通过 |
| Version Store | 13 | 通过 |

此外，`python -m compileall -q search_harness` 通过。

Controller 测试覆盖：

- 完整假 effect 闭环和 version advance；
- effect 局部重试，不重放已完成工作；
- effect 已落盘、完成事件未写入时的恢复；
- 重试耗尽后的显式 resume；
- Candidate Reviewer 修订先持久拒绝 pending iteration，再返回指定职责层；
- Reviewer 修订义务映射到 evidence、mechanism 或 implementation 输入；
- Reviewer `accept` 不能越过 token 成本门禁；
- candidate staging 按 digest 幂等；
- trial alias 不会被误认作第二份独立证据。

## 小样本真实运行

目录：`controller_run/`

配置为 10 个样本、每题 2 次 rollout。Incumbent 指标：

- accuracy `0.90`；
- stable correct `9/10`；
- stable failure `1/10`；
- Actor token `44,233`。

该运行真实调用了 Failure Analyst、Hypothesis Researcher、Intervention
Worker 和 Evidence Reviewer。它暴露了两个实现问题：

1. Worker artifact 同时以便利别名和编号 trial 传递，Reviewer 将同一路径判成
   重复证据。修复后显式 resume 只重试失败的 Reviewer，没有重跑 incumbent、
   Analyst、Researcher 或已完成 trial。
2. 试验选择器最初只允许 Analyst 引用的失败轨迹。Reviewer 要求同假设的独立
   反例后，候选池无法满足义务，运行以“无未使用匹配 prefix”安全结束。

对应修复：

- trial ledger 只接受 `trial_<数字>`，Worker 便利别名不进入证据集合；
- 选择器先使用 Analyst 引用，再按冻结 rollout 文件顺序回退到全部 rollout
  prefix；
- phase 由 Controller 匹配，语义不适合仍由 Worker 返回
  `unsuitable_assignment`，不会让 Controller 猜测语义。

小样本运行最终完成 10 个 effect，Controller effect token 合计
`440,069`，未产生候选，accepted version 保持 `harness_v0001`。

## 30 样本真实闭环

目录：`controller_run_broad_pool/`

### Incumbent

| 指标 | 值 |
| --- | ---: |
| Rollout | 60 |
| Accuracy | 0.80 (`48/60`) |
| Stable correct | 24/30 |
| Stable failure | 6/30 |
| Unstable | 0/30 |
| Mean steps | 2.1333 |
| Actor tokens | 153,410 |

Failure Analyst 识别出一类“检索一两次后，在关键属性或实体连接仍缺失时提前
结束”的稳定失败。初始 `post_tool` 假设在第一个 trial 中被证伪，Evidence
Reviewer 将工作返回原 Hypothesis Researcher session。修订后的假设使用
`pre_final` 的 `defer_final_answer`，随后两次 trial 通过证据评审并进入机制
蒸馏。

### 候选一

| 项目 | 值 |
| --- | --- |
| Iteration | `iteration_20260729T071648383118Z_612105c5` |
| Digest | `94e69ff7ffaa8a3d668c93120de85a74dda881aa9e55a125b0d73400c64502a3` |
| Validation | 通过 |
| Accuracy | 0.80 (`48/60`) |
| Stable correct | 22/30 |
| Stable failure | 4/30 |
| Unstable | 4/30 |
| Actor tokens | 154,366 |
| Reviewer | `revise → mechanism` |

Compiler 新增 `extensions/missing_evidence_search/plugin.py` 并修改
`harness.json`。Candidate Reviewer 检查 60 条轨迹后发现 Hook 实际激活次数为
0；aggregate accuracy 虽持平，稳定性变差，观察到的 improved/regressed case
不能归因于机制。Controller 因此先拒绝该 pending iteration，再返回机制层。

这条回边暴露出 Candidate Reviewer 的 `next_obligation` 当时只进入路由 payload，
Distiller/Compiler 没有消费。修复后的映射为：

- `evidence` → 下一试验义务；
- `mechanism` → `capability_constraints`；
- `implementation` → `implementation_constraints`。

### 候选二

| 项目 | 值 |
| --- | --- |
| Iteration | `iteration_20260729T072830891684Z_4e6ca71f` |
| Digest | `556f280c609c5c6181a1433498ff564a003b660d91b27af3765d8f60bfa3be0e` |
| Validation | 通过 |
| Accuracy | 0.75 (`45/60`) |
| Stable correct | 21/30 |
| Stable failure | 6/30 |
| Unstable | 3/30 |
| Mean steps | 2.1167 |
| Actor tokens | 147,430 |
| Reviewer | `accept` |
| Promotion gate | 拒绝，accuracy delta `-0.05` |

第二候选新增 `extensions/missing_search_intervention/plugin.py`。Reviewer 认为
实现合法且没有观察到误触发，给出 `accept`；但该候选在冻结 Experience Set
上的 accuracy 明确低于 incumbent。Controller 没有采用模型对“随机波动”的
解释，按配置的非模型门禁拒绝 iteration。

### 最终控制状态

| 项目 | 值 |
| --- | ---: |
| 完成 effect | 25 |
| 失败事件 | 3 |
| 暂停 / 显式恢复 | 1 / 1 |
| Controller effect token | 2,858,414 |
| Pending iteration | 0 |
| Accepted version | `harness_v0001` |
| Run 终态 | completed，candidate rejected |

三次失败事件中，两次来自运行中修改 Teacher contract manifest 造成的
`hypothesis_researcher@2` 注册不一致。这是本次开发测试的中途干预，不是正常
运行路径；修正 contract 声明后显式 resume 从失败 Researcher 局部继续。

另一次是为了验证新反馈映射而在 Candidate Reviewer effect 尚未落盘时停止进程。
恢复后 Controller：

1. 保留已经提交的第二候选 60 条 rollout 与 evaluation artifact；
2. 把未提交的 Reviewer effect 记录为 `InterruptedExecution`；
3. 只重试 Reviewer；
4. 完成确定性拒绝。

这验证了 `effect.json` 提交边界和事件回放恢复语义。

## 已验证边界

本次结果支持以下工程结论：

- 七角色可以由局部转移组成正式闭环，无需 v1 式长函数固定 workflow；
- 角色只做局部语义判断，预算、重试、版本写入和 promotion 仍由控制面决定；
- Reviewer 修订、Compiler 校验失败、Worker assignment 不适合等结果可以返回
  对应职责层，不需要角色输出 `next_role`；
- 已完成 effect 不会因进程恢复而重放；
- pending candidate 在每条终止或修订路径上都会被接受或拒绝；
- 模型的 `accept` 建议不能绕过准确率和成本门禁。

## 不应从本次实验推出的结论

- 30 个样本、每题 2 次 rollout 只适合工程闭环验证，不足以证明候选机制的
  泛化收益；
- 本次没有候选晋升，不能据此声称当前机制改善了 Student；
- Teacher 角色没有对同一完整输入独立运行 3 次，因此不能声称角色行为稳定；
- 第二候选的 `-0.05` 可能同时包含模型随机性和候选影响，但 promotion gate
  无需先区分因果归属：低于冻结阈值就应拒绝；
- 当前仍是单进程、单写入者、单候选 Controller，未验证多候选并行或分布式
  调度。

若后续目标从“控制闭环正确”转为“找到可晋升机制”，应扩大冻结 Experience
Set、增加重复数，并把 Hook 激活覆盖率作为进入昂贵全量候选评估前的显式证据
义务，而不是放宽 promotion gate。
