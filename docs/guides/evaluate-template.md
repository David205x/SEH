# 评估一组 Rollout

根 `evaluate` 命令评估已有 Rollout JSONL，不负责生成它。Evolution Controller 会自动生成 incumbent/candidate Rollout；独立批量运行可通过 `search_harness.evaluation.run_examples()` 以相同记录格式写出。

## 静态评估

```powershell
python -m search_harness evaluate path\to\rollouts.jsonl `
  --output-dir path\to\evaluation
```

输出目录应出现 `summary.json`、`per_example.jsonl`、`per_rollout.jsonl` 和 `summary.md`。

## 启用 Teacher Judgment

```powershell
python -m search_harness evaluate path\to\rollouts.jsonl `
  --output-dir path\to\evaluation `
  --teacher-judge `
  --judge-workers 8 `
  --env-file .env
```

Teacher 只处理静态规则不能确定的答案。若要比较两个 Template：

1. 使用完全相同的 Evolution Set。
2. 使用相同 replicate 数、seed 规则、Student 配置和 Judge 配置。
3. 保留每批记录的 `harness` 与 `provenance`。
4. 同时查看 accuracy、稳定性、runner error 与 token/step/tool 指标。

不要仅比较两次随机运行的最终准确率；Hook 是否触发、行为是否符合机制由 trace 与 Conformance 证据回答。
