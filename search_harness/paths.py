"""项目级 Template、Checkpoint 与运行产物路径约定。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


HARNESS_TEMPLATES_ROOT = Path("harness_templates")
ACTOR_TEMPLATE_ROOT = HARNESS_TEMPLATES_ROOT / "actor" / "baseline" / "plugins"
CRITIC_TEMPLATE_ROOT = (
    HARNESS_TEMPLATES_ROOT / "adapter" / "critic" / "baseline" / "plugins"
)
COMPILER_TEMPLATE_ROOT = (
    HARNESS_TEMPLATES_ROOT / "adapter" / "compiler" / "baseline" / "plugins"
)
INTERVENTION_COORDINATOR_TEMPLATE_ROOT = (
    HARNESS_TEMPLATES_ROOT
    / "adapter"
    / "intervention_coordinator"
    / "baseline"
    / "plugins"
)
HARNESS_CHECKPOINTS_ROOT = Path("harness_checkpoints")
DEFAULT_CHECKPOINT_STORE = HARNESS_CHECKPOINTS_ROOT / "search_actor"
RUNS_ROOT = Path("runs")
COMPONENT_RUNS_ROOT = RUNS_ROOT / "components"
EXPERIMENT_RUNS_ROOT = RUNS_ROOT / "experiments"


def new_component_run_dir(component: str) -> Path:
    """返回一个按 UTC 时间命名的组件调试运行目录。"""

    normalized = component.strip().lower()
    if not normalized or any(
        character not in "abcdefghijklmnopqrstuvwxyz_" for character in normalized
    ):
        raise ValueError("component name must contain only lowercase letters and underscores")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return COMPONENT_RUNS_ROOT / normalized / timestamp
