# 编写 Component

## 1. 选择正确类型

- Tool：提供外部动作或读取能力。
- Prompt：把 AgentState 转成 ModelInput。
- Output：把模型文本转成 ParsedOutput。
- Extension：在稳定 lifecycle phase 观察或修改运行行为。

不要把完整 Harness 写成一个 Component，也不要为了可能的未来变体先增加 Plugin 层。

## 2. 在模板内建立入口

单例 Prompt 和 Output 分别放在模板的 `prompt/` 与 `output/`；可重复的 Tool 和 Extension 分别放在 `tools/<component_id>/` 与 `extensions/<component_id>/`。每个 Component 入口导出 `build(...)` Factory。Factory 使用显式参数与 `ComponentFactoryContext`，不要读取隐式全局路径；文本文件显式以 UTF-8 读写。

Extension 示例骨架：

```python
from search_harness.framework import BaseHook, HookContext, HookPhase


class ExampleHook(BaseHook):
    def handle(self, context: HookContext) -> None:
        if context.phase == HookPhase.PRE_FINAL:
            decision = context.state.get("stage.final_decision")
            # 只在满足已定义机制时 set 新的 FinalDecision。


def build(config, context):
    return ExampleHook(
        hook_id="example",
        phases=frozenset({HookPhase.PRE_FINAL}),
        writable_stage_keys=frozenset({"stage.final_decision"}),
    )
```

实际 Factory 参数以同类型现有 Component 和 Assembly 测试为准。Hook 若需要持久状态，使用 `StateRef` 声明；若需要模型，声明 profile 和调用预算。不要直接修改 `AgentState` 或绕过 `HookContext`。

### Compiler-facing Runtime Input Topics

Mechanism Distiller 不填写 Framework symbol，而是在每条 phase rule 的 `runtime_inputs` 中选择 `task`、`conversation`、`tool`、`model_io`、`parsed_output`、`final_decision`、`trajectory`、`persistent_state` 等受控 Topic。Topic 是覆盖度声明：例如 `tool` 会把当前 Tool Call/Result、已完成交互历史、相关类型、phase 生命周期与推荐用法一并加入 capability packet，避免由自由文本猜接口。Compiler 应优先使用 packet 内的 Python type hint、docstring、注释和 reference Hook；`query_hook_api` 用于重取完整 Topic、查询精确 symbol 或获得拼写建议，不负责替代 packet 的基础覆盖。

## 3. 注册与 Policy

在 `harness.json` 对应数组中加入唯一 `instance_id`、模板内 entrypoint 和配置。进入 Evolution 的模板还要在 `evolution.json` 把该 ID 标为 `fixed` 或 `evolvable`。

## 4. 验证

```powershell
python -m search_harness template validate path\to\template --env-file .env
```

随后运行最小的针对性测试：Factory 返回类型、Manifest 装配、订阅 phase、状态写权限、触发与不触发路径、异常 trace。只有需要验证真实 API 适配时才运行模型调用；测试机制正确性时不要调整 Prompt 追求准确率。
