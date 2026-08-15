# as_you_can

本目录用于在不修改项目既有代码、文档和 artifact 的前提下，独立开发与评估 qwen3-8b 检索推理 Harness Template。

## 边界

- 模型固定为项目 `.env` 中的 Student 模型（qwen3-8b）。
- 模板不读取数据集答案，也不依赖外部 API 模型。
- `train` 子集用于开发和消融；`heldout` 只用于最终冻结模板的验证。
- 所有新增脚本、模板、rollout、评测报告和研究记录均保存在本目录。

## 最终产物

- 最终模板：`final_template/`
- 可移植 ZIP：`artifacts/as_you_can_final_template.zip`
- 完整实验报告：`EXPERIMENT_REPORT.md`
- 冻结模板 digest：`515afd66017c6c88cdc6418044fce71cdaa522e90ba8d80f8f4cfe9386dd5579`
- ZIP SHA-256：`05FC01144D67DC48859E9A5E310A683FC4EB92551B1EC4441DD0E11BD9740769`

## 验证模板

从项目根目录执行：

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe -m search_harness template validate `
  experiments/as_you_can/final_template --env-file .env
```

## 运行单题

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe -m search_harness run `
  "Who developed the first wearable pacemaker?" `
  --template-root experiments/as_you_can/final_template `
  --env-file .env
```

## 复现训练集 100 条跑批

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe `
  -m experiments.as_you_can.run_benchmark `
  --template experiments/as_you_can/final_template `
  --name train100_reproduction `
  --dataset train --limit 100 --selection-seed 20260815 `
  --workers 6 --max-steps 20
```

Teacher Judge 是离线评分器，并非模板依赖：

```powershell
D:\ProgramData\miniconda3\envs\env_search_harness\python.exe -m search_harness evaluate `
  experiments/as_you_can/artifacts/benchmarks/train100_reproduction/rollouts.jsonl `
  --output-dir experiments/as_you_can/artifacts/benchmarks/train100_reproduction/evaluation_teacher `
  --teacher-judge --judge-workers 8 --env-file .env
```

## 问题路由与自适应分解更新

准确率优先的最新推荐模板为 `final_template_routed_adaptive/`，可移植包为
`artifacts/as_you_can_routed_adaptive_template.zip`。原 `final_template/` 保留为低成本版本。

- train100：Teacher semantic `61% -> 68%`，EM `47% -> 56%`。
- frozen heldout100：Teacher semantic `52% -> 60%`，EM `35% -> 40%`。
- 新模板仍只使用本地 qwen3-8b；Teacher Judge 只用于离线评分。
- 详细消融、三次 Judge 复核和成本见 `ROUTED_DECOMPOSITION_EXPERIMENT.md`。

新模板源码树 SHA-256：
`979afdc44d6073a169f5bb628dd9474bbfd9227173aa3b9dc8d4d69f57e230c2`

ZIP SHA-256：
`6c56d7e8f160e67a61ad4be3163e4bd52fb92163e2ec8c7de285cd972dc164e3`
