# Harness Template 与 Evolution Policy

Harness Template 是一个可移植目录。根目录必须包含 UTF-8 `harness.json`；若要进入 Evolution，还必须包含 UTF-8 `evolution.json`。Component 源文件位于模板内部。

## `harness.json`

当前 `schema_version` 为 `1`，根字段严格限制为：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | positive integer | 必须为 1 |
| `harness_id` | non-empty string | 模板内 Harness 稳定 ID |
| `tools` | array | 零个或多个 Tool 声明 |
| `prompt` | object | 唯一、必须启用的 Prompt 声明 |
| `output` | object | 唯一、必须启用的 Output 声明 |
| `extensions` | array | 有序 Extension 声明，默认空数组 |

每个声明包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `instance_id` | non-empty string | 在整个 Manifest 内唯一 |
| `entrypoint` | string | `relative/path.py:factory_name`，不得越出模板根目录 |
| `config` | object | 传给 Component Factory 的配置 |
| `enabled` | boolean | 可选，默认 `true`；Prompt/Output 不可禁用 |

示例：

```json
{
  "schema_version": 1,
  "harness_id": "baseline_search",
  "tools": [
    {
      "instance_id": "search",
      "entrypoint": "tools/retriever_search/component.py:build",
      "config": {}
    }
  ],
  "prompt": {
    "instance_id": "simple_search",
    "entrypoint": "prompt/component.py:build",
    "config": {}
  },
  "output": {
    "instance_id": "tagged_output",
    "entrypoint": "output/component.py:build",
    "config": {}
  },
  "extensions": []
}
```

未知字段、重复 `instance_id`、绝对入口路径和 `..` 路径均会拒绝加载。

## 目录布局

正式模板使用以下浅层布局：

```text
<template_root>/
├─ harness.json
├─ evolution.json                 # 仅可进化模板需要
├─ prompt/                        # 唯一 Prompt Component 及其资产
│  ├─ component.py
│  └─ ...
├─ output/                        # 唯一 Output Component
│  └─ component.py
├─ tools/<component_id>/          # 零个或多个 Tool Component
│  └─ component.py
├─ extensions/<component_id>/     # 零个或多个 Extension Component
│  └─ component.py
└─ examples/                      # 可选、非运行时示例输入
```

Prompt 和 Output 是 Manifest 单例，因此目录不重复 `instance_id`；Tool 和 Extension 是可重复集合，每个 Component 保留独立目录作为代码与资产所有权边界。不存在的可选类别不创建空目录。

## `evolution.json`

当前 `schema_version` 为 `1`。`harness_id` 必须与 Manifest 相同；`components` 把每个 Manifest `instance_id` 映射为：

- `fixed`：Evolution 不得修改。
- `evolvable`：Candidate 可以修改。

Policy 必须完整覆盖所有 Component，不能包含不存在的 ID。Policy 控制修改权限，不改变装配顺序或运行行为。

## Teacher Template

Teacher Template 同样使用共享 `harness.json` 和 Assembly，但会附带角色声明、Prompt 和资源工具。Teacher 的模板资产位于 `harness_templates/teacher/<role_id>/`，不嵌入 Framework 包。稳定角色协议由代码定义，模板不能自行改变输入/输出 contract。

Teacher Prompt 的 `config` 支持：

- `instructions`：相对于 `prompt/` 的初始 system instruction 文件。
- `user_template`：相对于 `prompt/` 的初始 user message 模板。
- `continuations`：可选的反馈来源到续接模板文件映射；每个模板必须且只能包含一个 `{{feedback_event}}`，运行时以 UTF-8 JSON 替换该占位符。

续接模板属于接收反馈的目标角色。例如 Hypothesis Researcher 的 Evidence Reviewer 回流 Prompt 位于其自身 `prompt/continuations/`，Runner 只根据已经确定的反馈来源选择并渲染模板，不由 Prompt 决定路由。

## 校验

`template validate` 会检查 Manifest、Evolution Policy、入口加载、Factory 返回类型、Hook 声明与模板内部边界。进入 Candidate Attempt 后还会计算内容 digest，并把完整 Validation Report 记录为事件。
