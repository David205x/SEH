"""装配完成的 Harness 与一次运行的 Harness Instance。"""

from __future__ import annotations

from dataclasses import dataclass

from ..agent.types import AgentState
from ..tools import ToolExecutor
from ..trajectory import InMemoryTrajectoryRecorder
from .components import OutputParser, PromptBuilder
from .lifecycle import HookPipeline
from .state import HookStateStore


@dataclass(frozen=True)
class Harness:
    """可复用且不保存单次运行状态的 Harness 组合对象。"""

    prompt: PromptBuilder
    output: OutputParser
    tool_executor: ToolExecutor
    lifecycle: HookPipeline

    def instantiate(self, run_input: str, *, max_steps: int) -> "HarnessInstance":
        """为一次 Agent Run 创建隔离状态与 Trajectory。"""

        state = AgentState(question=run_input, max_steps=max_steps)
        trajectory = InMemoryTrajectoryRecorder()
        lifecycle_state = self.lifecycle.begin_run(state)
        return HarnessInstance(
            harness=self,
            state=state,
            trajectory=trajectory,
            lifecycle_state=lifecycle_state,
        )


@dataclass(frozen=True)
class HarnessInstance:
    """一次 Agent Run 所有的 Harness State 与 Extension State。"""

    harness: Harness
    state: AgentState
    trajectory: InMemoryTrajectoryRecorder
    lifecycle_state: HookStateStore
