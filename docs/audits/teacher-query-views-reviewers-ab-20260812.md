# Trial Reviewer 与 Evidence Reviewer 查询视图 A/B

日期：2026-08-12  
结论状态：Trial Reviewer 影子方案已放弃；Evidence Reviewer 暂不正式迁移

## 1. 范围

上一轮只接入 Hypothesis Researcher 和 Intervention Worker。本轮补充：

- Trial Reviewer：保留完整 Trial Artifact，影子 `get_trial_evidence` 返回围绕冻结 Phase
  的 Judgment View，并保留 `get_trial_event` 精确下钻；
- Evidence Reviewer：它没有查询工具，因此保留完整 `EvidenceReviewerInput` Artifact，
  只把传给模型的初始输入改为表格、紧凑 JSONL 和短文本混合视图。

正式与影子使用相同 Role Input、Resource Config、DeepSeek 配置、Role Budget 和 Output
Contract。实验没有重跑 Intervention 或 Student，也没有修改源 Artifact。

## 2. 历史基线

`20260809_base` 中：

- Trial Reviewer 84/84 最终完成，82/84 首次提交通过；
- Evidence Reviewer 21/21 最终完成，仅 4/21 首次提交通过；
- Evidence Reviewer 的历史修订几乎都来自 `phase_findings[].assessment`、整体
  `assessment` 或 `next_obligation` 超过长度上限。

因此 Trial Reviewer 已接近通过率天花板，Evidence Reviewer 才有明显的首次通过率提升
空间。

## 3. 实验设计

Trial Reviewer 选择一个正触发 Trial 和一个正确不触发 Trial，每个正式/影子各运行
三次。Evidence Reviewer 选择分别包含 4、8、12 条 Trial Review 的输入，每个正式/影子
各运行三次。首轮共 30 次 DeepSeek Role Run。

首轮完整结果：
`runs/experiments/teacher_query_views/20260812_reviewer_ab_deepseek/summary.json`。

正触发 Trial 的影子视图发生立即动作误读后，又把默认事件目录收窄到 fork 证据和
phase 的立即后继动作，额外正式/影子各运行三次。复测结果：
`runs/experiments/teacher_query_views/20260812_trial_reviewer_shadow_refined/summary.json`。

## 4. Trial Reviewer 结果

### 4.1 首轮

| Scheme | Runs | Final pass | First-submit pass | Mean total tokens |
| --- | ---: | ---: | ---: | ---: |
| formal | 6 | 6/6 | 6/6 | 20969.17 |
| shadow | 6 | 6/6 | 6/6 | 42936.83 |

正确不触发 Trial 表现符合预期：两套均三次判为 `negative +
correct_non_intervention`。影子总 token 从平均 `11481` 降到 `8529`，下降 `25.7%`。

正触发 Trial 中，两套均三次提交 `positive + intervention_applied`，但影子一次把后续终答
误读为干预后的立即动作，形成语义错误。影子模型频繁调用 `get_trial_event`：平均 13 次，
正式为 3 次，使正例平均总 token 从 `30457` 上升到 `77345`。

### 4.2 收窄事件目录复测

收窄后两套仍 3/3 最终完成，但：

| Scheme | Final pass | First-submit pass | Mean queries | Mean total tokens |
| --- | ---: | ---: | ---: | ---: |
| formal | 3/3 | 3/3 | 3.00 | 33545.33 |
| shadow | 3/3 | 2/3 | 10.33 | 91408.00 |

三次影子输出都正确识别立即下一动作为 Search，语义误读得到修正；但模型仍会自行请求
默认目录没有列出的后续 Event Index。只缩短默认目录不能约束自由下钻，token 为正式的
`2.72` 倍，并新增一次长度校验修订。

结论是 Trial Reviewer 的通过率没有上升。负例受益于紧凑默认视图，正例却因自由逐事件
读取而显著退化。若要稳定，需要在后续设计中二选一：让 Judgment View 本身包含判断所需
的完整立即证据并取消自由 Event 工具，或把 Event 工具参数改成视图明确发放的引用白名单。
这属于查询能力协议变化，不能作为本次影子实验的普通补丁实施。

## 5. Evidence Reviewer 结果

| Scheme | Runs | Final pass | First-submit pass | Mean retries | Mean total tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| formal | 9 | 9/9 | 2/9 | 1.00 | 26233.56 |
| shadow | 9 | 9/9 | 1/9 | 0.89 | 21177.11 |

最终通过率均为 100%，首次提交通过率没有上升：正式 `22.2%`，影子 `11.1%`。影子平均
总 token 下降 `19.3%`，平均修订次数从 `1.00` 小幅降到 `0.89`，但样本不足以证明该差异
稳定。

所有影子校验失败仍来自既有长度约束：`phase_findings[0].assessment` 多为 514–567
字符，偶尔伴随整体 assessment 超过 1200 字符。视图压缩改善输入成本，却没有改变模型
对 Output Contract 长度的遵循。因为角色没有查询工具，该问题也不能由 Tool Result
排版解决；需要单独处理输出生成纪律，例如更明确地按目标长度写作，或采用结构化的
程序摘要字段减少自由文本职责。

两套 Evidence Reviewer 在所有配对中作出一致的总体 Decision：4、8 Trial 输入均为
`continue`，12 Trial 且预算耗尽的输入均为 `revise`。因此影子输入没有造成路由语义
漂移，但不能声称提升通过率。

## 6. 结论

本次接入没有提高通过率：两角色最终通过率原本就是 100%；首次提交通过率方面 Trial
Reviewer 持平或复测下降，Evidence Reviewer 从 2/9 降为 1/9。影子 Evidence 输入有
约 19% token 收益，Trial 负例有约 26% token 收益，但 Trial 正例的自由下钻导致总体
成本和稳定性退化。

因此当前影子 Reviewer 方案不应切换到正式路由。值得保留的是实验代码、确定性视图和
失败证据；正式设计应先解决 Trial Event 的读取边界，以及 Evidence Reviewer 的自由
文本长度遵循，再进行新的 A/B。

所有源 Artifact 的运行前后 SHA-256 一致。

## 7. 跨 Artifact 复测

为验证 Evidence Reviewer 的约 `19%` 收益是否可重复，另选取四份既有 Role Artifact，
覆盖历史 `continue`、`ready_to_distill`、`reject`、`revise` 四种结论。正式与影子初轮各
运行三次；对出现成本反向、总体决策或 phase status 波动的三组再各补两次。最终共得到
18 对正式/影子真实 API 运行。源 Artifact 均保持不变。

初轮 12 对运行中，影子平均总 token 从 `37746.58` 降至 `28607.17`，下降 `24.2%`；
但补测后合计 18 对的平均值从 `37727.78` 降至 `30230.22`，下降 `19.9%`，中位数只
下降 `11.2%`。影子首次请求的 prompt token 稳定下降 `15.2%`，而首次 completion token
反而增加 `7.7%`；总体约 `20%` 的收益主要受结构化提交重试次数的随机波动放大。

按输入分组观察并不稳定：四组中两组节省，两组反向增加。三组补至五次后，正式/影子
平均总 token 分别为：`continue` 组 `19349.8 / 19822.4`，反证组
`41012.4 / 46163.4`，预算边界组 `57808.2 / 30395.4`。稳定的
`ready_to_distill` 三次组为 `29416.0 / 20746.0`。

18 对运行全部最终完成，正式与影子首次提交通过均为 `6/18`；总体 Decision 配对一致
`15/18`，phase status 配对一致 `16/18`。其中反证组两套方案在五次运行中都得到
`revise` 两次、`reject` 三次，只是配对次序不同，表明这部分首先是角色在两个合法修订
路由之间的固有波动。预算边界组则出现 `supported`、`inconclusive`、`unsupported` 的
局部标签波动，无法证明影子视图保持了稳定的 phase 判断。

因此，“Evidence Reviewer 在总体上约节约 20% token”是成立的样本均值，但“在效果
稳定时稳定节约约 20%”不成立。当前仅能确认模型首轮可见输入稳定缩短约 15%；总成本
和局部语义没有达到正式迁移条件。Evidence Reviewer 影子实现保留用于继续诊断，暂不
切换正式路由。

跨 Artifact 初轮与补测分别保存在：

- `runs/experiments/teacher_query_views/20260812_evidence_reviewer_cross_artifact_ab/summary.json`
- `runs/experiments/teacher_query_views/20260812_evidence_reviewer_cross_artifact_extension/summary.json`

Trial Reviewer 的影子代码已经删除，不再作为候选实现；历史实验 Artifact 和本报告保留，
用于说明为什么放弃该方案。
