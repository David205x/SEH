# START-001-SNAPSHOT-v1

冻结时间：2026-08-20T13:00:00+08:00

## 输入

- 研究范围：Evidence-Gated Harness Evolution，固定 Student 参数、Evaluator 与基础 Loop，仅演化 Prompt、Tool、Parser、Lifecycle Hook。
- 用户主张来源：`0820_report.md` 与本轮三段中文方案表述。
- 代码状态：`main@71df3e1`，工作树存在大量用户未提交改动；当前代码含 Evidence Gate、Mechanism Distiller、Hook Feasibility、Compiler、Conformance、Candidate Evaluation、typed rerouting。
- 实验状态：`runs/evolution/20260815_qwen3-8b_hook_feasibility/` 证明 feasibility routing 可运行；两个完整 Candidate 均低于 incumbent，第二个在 Candidate Review 前因 soft token budget 暂停。

## 冻结证据

- 文献：`.cvpr/literature/文献注册表.jsonl` 的 P001-P016。
- 问题状态：`.cvpr/literature/问题状态矩阵.yaml`。
- 候选卡：`.cvpr/start_artifacts/候选IDEA证据卡.md` 的 IDEA-001 至 IDEA-006。

## 审查硬约束

1. 不得把 fork/replay、falsifiable hypothesis、candidate gating、guard/intervention、event receipt 视为首创。
2. 不得把当前 gate-operability 或历史 replay 当作最终 utility/cost 已获证实。
3. 必须检查 Shepherd 与 HarnessBank 是否实质吞并 pre-compilation evidence novelty。
4. 必须检查 P006/P013 是否足以支持 Student realizability gate 的问题重要性，但不得把 diagnosis paper 误称为 optimizer method。
5. 最终计划必须包含 P016 要求的 budget-matched simple baselines 与 held-out tasks。
