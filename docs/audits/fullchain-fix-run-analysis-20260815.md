# 20260815 fullchain fix Run 分析

## 范围

新 Run `runs/evolution/20260815_qwen3-8b_fullchain_fix` 复用
`20260815_qwen3-8b_fullchain` 的完整 Incumbent Evaluation。复用工作保留原始
`579,635` token usage，但在新 Run 的 Controller 账本中计费为 `0`。新 Run 使用独立
Version Store，并由当前 `config/runtime.yaml` 重新生成 Control/Effect 配置。

本次未修改 Student Template、Teacher prompt、角色协议或运行产物。Run 在第三个
mechanism 的第 5 次 Compiler revision 开始后由操作者中断；当前 agenda 可用普通
`evolve resume` 恢复。

## 基线

Incumbent `harness_v0001` 在 75 个 example、每题 3 次 rollout 上的结果为：

| 指标 | Incumbent |
| --- | ---: |
| Accuracy | 0.6711 (151/225) |
| Stable correct | 42 |
| Stable failure | 17 |
| Unstable | 16 |
| Total tokens | 579,635 |

新 Version Store 仍只有 `harness_v0001`，没有 Candidate 晋升。

## 已完成流程

截至中断，Run 完成 78 个 WorkItem，累计计费 `11,430,330` tokens：

| Work kind | 完成数 | Tokens | 占比 |
| --- | ---: | ---: | ---: |
| Compiler | 11 | 4,428,850 | 38.7% |
| Conformance Reviewer | 11 | 2,006,582 | 17.6% |
| Candidate Evaluation | 2 | 1,936,415 | 16.9% |
| Evidence Reviewer | 6 | 856,365 | 7.5% |
| Intervention | 6 | 552,286 | 4.8% |
| Candidate Reviewer | 2 | 502,312 | 4.4% |
| Distiller | 3 | 492,139 | 4.3% |
| Researcher | 5 | 394,301 | 3.4% |
| Failure Analyst | 3 | 261,080 | 2.3% |

Compiler 与 Conformance Reviewer 合计 `6,435,432` tokens，占总消耗 `56.3%`。
配置没有 `max_total_tokens`，因此 token 预算没有确定性上限；`max_work_items=200`，
中断时已调度 79、完成 78，名义上仍可调度约 121 个 WorkItem。当前 mechanism 已开始
第 5/10 次 Compiler revision。

## Candidate 结果

| Candidate | Accuracy | Delta | Total tokens | 相对基线 | Hook tokens | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `prefinal_deferral` | 0.6533 | -0.0178 | 1,028,964 | 1.78x | 550,200 | reject |
| `pre_final_absence_gate` | 0.6400 | -0.0311 | 907,451 | 1.57x | 521,752 | reject |

第一个 Candidate 的 Hook 实际触发 7 次，只有 1 次可归因地纠正答案；3 次违反负例
边界，另 3 次干预后仍错误。第二个 Candidate 只有 2 次正触发，均为误触发；其中一次
把正确答案改错。两个 Candidate 中所有其他表面改善均发生在 Hook 未触发路径，无法
归因于 mechanism。

两个送入全量评估的 Candidate 都固定使用 `thinking_mode="enabled"`。其 Hook token
分别超过或显著高于 Student token。Compiler 曾对 enabled/disabled 做局部实验，但按
少量分类 control 选择 enabled；这些 control 没有预测真实分布上的误触发、收益和全局
调用成本。

第三个 mechanism `evidence_deferral` 首版使用 disabled，后因正例漏判改为 enabled；
其 Conformance faithful 数依次为 `12/24 -> 13/24 -> 19/24 -> 9/24`。第四版切回
disabled 后明显退化，随后开始第五次 Compiler revision。该序列显示边界调优在两种
thinking mode 与正负召回之间振荡，尚未收敛。

## 是否改善

### 已改善的控制面

- Incumbent Evaluation 可被完整复用，并使用独立 Run/Version Store 与当前 runtime
  配置；基线没有重复计费或重跑。
- Evidence Review 没有复现“提出 Trial Selector 无法满足的 obligation 后耗尽预算”
  的死循环。第三个研究方向完成 4 个不同 trial、2 次 Researcher 修订后才进入 Distiller。
- Candidate 被拒后能够回到新的 Failure Analyst/Researcher 路线，不再因缺少路由目标
  中断。
- Compiler 没有提交未修改 workspace；同一 mechanism 的 revision 能继承 workspace。
- Conformance preflight 在全量 Candidate Evaluation 前拒绝了多份不忠实或局部有害
  Candidate，避免为每个失败 revision 都支付 225 条 rollout。

### 未改善的效果面

- 两个完整 Candidate 均降低准确率并显著增加 token，没有产出 Accepted Version。
- 前两个研究方向仍在单个 trial 后直接 distill；边界探索被推迟给
  Compiler/Conformance。
- 第三个方向虽有 4 个 trial，仍发生多轮 Hook-model evaluator 调优；更多研究证据未
  自动转化为更少 Compiler revision。
- Compiler 的模型实验没有独立调用次数/token 预算，且 enabled thinking 的选择缺少
  “必须由显著收益覆盖全局成本”的约束。
- Conformance 能识别失配并给出具体反馈，但其多轮语义审查本身已成为第二大 token
  来源。
- 跨 research attempt 的经验尚未自动提供给后续角色；前两个 Candidate 已证明
  thinking-enabled 分类 Hook 高成本且无收益，第三方向仍重新经历相同取舍。

## 结论

本次修改改善了流程的可恢复性、路由完整性和坏 Candidate 的前置拦截，但没有改善最终
进化效果，也没有降低总成本。新 Run 在 78 个已完成 WorkItem 时已超过旧 Run 完整
99 个 WorkItem 的 `9,567,841` tokens。继续当前 Run 的主要增量信息只会是第三个
Hook-model evaluator 能否在更多 Compiler revision 后收敛；鉴于前四版发生明显振荡，
且两个完整 Candidate 已给出一致负结果，本次对照目标已经得到充分回答，中断是合理的。

