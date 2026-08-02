"""通过通用 Agent Loop 执行同步 Agent Run。"""

from __future__ import annotations

from .agent import Agent
from .loop import AgentLoop
from .types import RunResult


class LoopRunner:
    """通过通用 Agent Loop 驱动 Harness Lifecycle。"""

    def __init__(self, *, max_steps: int) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.max_steps = max_steps

    def run(self, agent: Agent, run_input: str) -> RunResult:
        instance = agent.harness.instantiate(run_input, max_steps=self.max_steps)
        return AgentLoop(agent=agent, instance=instance).run()
