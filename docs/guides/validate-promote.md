# 校验并晋升 Candidate

正式 Evolution Run 会自动完成以下过程；本指南用于理解检查点，不建议手工绕过 Controller 晋升。

## Candidate 生命周期

1. Mechanism Compiler 产出 Candidate Template 文件编辑并启动 Candidate Attempt。
2. Candidate Workspace 以当前 Accepted Template Version 为父版本重放编辑。
3. Candidate Validation 检查 Manifest、Policy、入口、Factory、Hook 与路径边界。
4. Conformance Reviewer 在参考 trial 对应样本上验证实现语义。
5. 使用冻结 Evolution Set 运行 Candidate Evaluation。
6. Candidate Reviewer 判断观察效果，必要时指定修订层级。
7. Promotion Gate 检查 Reviewer recommendation、validation、准确率增量和 token 比率。
8. 通过后 Version Store 原子物化、Git commit，并记录新的 Accepted Version；否则记录 reject。

## 审查重点

- `candidate_digest` 与被评估 workspace 一致。
- Validation Report 没有被忽略的错误。
- Conformance 至少观察到机制应触发的 phase，并能关联参考 trial。
- 新机制在 candidate trajectory 中实际触发；零触发不能证明有效。
- incumbent 与 candidate 的数据、replicate、seed 和 judge 配置一致。
- 准确率下降或成本越界时，Reviewer 的 `accept` 不能绕过 Gate。
- `revise` 的 obligation 只回流到 evidence、mechanism 或 implementation 之一。

## 手工只读核验

查看 Run 的 `events.jsonl`、对应 `artifacts/`、Version Store 的 `.harness-store/candidate_attempts.jsonl` 与 `versions.jsonl`。Accepted Version 应出现新的 `harness_vNNNN` 和 Git commit；被拒候选不应改变 Store 的最新 accepted template。

若要独立检查模板，使用 `template validate`。不要直接编辑 Version Store 的 `template/`、JSONL 日志或 Git 历史；这些文件共同构成可恢复与可审计边界。
