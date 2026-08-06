# 运行 Evolution Experiment

## 1. 初始化 Version Store

只需对一个新 Store 执行一次：

```powershell
python -m search_harness version-store init `
  --template-root harness_templates/student/baseline `
  --version-store harness_checkpoints/search_student `
  --env-file .env `
  --summary "Initialize Student template"
```

该命令校验模板并创建 `harness_v0001`。如果目录已初始化，不要再次 init。

## 2. 启动一个有界 Run

```powershell
python -m search_harness evolve start `
  --run-dir runs/evolution/example_run `
  --version-store harness_checkpoints/search_student `
  --dataset-path path\to\supported.jsonl `
  --limit 20 `
  --env-file .env
```

启动前在 `config/runtime.yaml` 的 `evolution.control` 与 `evolution.effects` 中设置
Generation、Trial、重试、并发和重复 Rollout 等超参数。创建 Run 时这些值会冻结到
`run.json`。首次工程验证建议先用小 `--limit` 和一代预算确认协议与服务稳定；真实
效果实验再增加样本和预算，不要改 Teacher prompt 或产物来强制推进。

## 3. 观察与恢复

Run 目录中的 `run.json`、`experience_set.jsonl`、`events.jsonl` 和 `artifacts/` 必须整体保留。进程中断后运行：

```powershell
python -m search_harness evolve resume runs/evolution/example_run --env-file .env
```

Controller 会重建 agenda，复用完整 effect artifact，并从未完成的工作继续。不要手动删除单个失败 work artifact 或拼接多个 Run。

## 4. 解释终态

`completed` 可能表示候选已接受，也可能表示证据不可蒸馏、预算耗尽或候选被拒。以 CLI reason、最后的 ControlEvent、Candidate Attempt 状态和 Version Store 最新版本共同判断；不能只看进程退出成功。
