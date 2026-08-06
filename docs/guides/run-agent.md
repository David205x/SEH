# 运行一个 Agent

## 前置检查

确认 `.env` 至少包含 `STUDENT_BASE_URL` 与 `STUDENT_MODEL_ID`；需要鉴权时设置 `STUDENT_API_KEY`。先做不调用模型的模板校验：

```powershell
python -m search_harness template validate harness_templates/student/baseline --env-file .env
```

## 执行

```powershell
python -m search_harness run "Who developed the first wearable pacemaker?" --env-file .env
```

保存完整 UTF-8 trace：

```powershell
python -m search_harness run "Who developed the first wearable pacemaker?" `
  --env-file .env `
  --trace-file runs/components/student/manual_trace.json
```

要验证另一套模板，使用 `--template-root`。要用 Teacher API 驱动相同的通用 Loop，可传 `--model-role teacher`；这不是执行 Teacher Role，Teacher Role 还需要其结构化输入与资源 Runner。

## 判断结果

CLI 先输出终态 status，再输出 answer 或 error。常见非完成状态包括工具错误和达到最大 step。排障时检查 trace 中最后一个 `model_input`、`model_output`、`parsed_output` 和 Hook/Tool 事件，不要通过修改输出内容掩盖错误。
