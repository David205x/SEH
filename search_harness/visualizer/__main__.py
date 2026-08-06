"""Run the local trace visualizer."""

from __future__ import annotations

import argparse
from pathlib import Path
from search_harness.paths import (
    COMPONENT_RUNS_ROOT,
    DEFAULT_CHECKPOINT_STORE,
)

from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--student-runs-dir",
        dest="student_runs_dir",
        type=Path,
        default=COMPONENT_RUNS_ROOT / "student",
        help="Directory containing standalone Student runs.",
    )
    parser.add_argument(
        "--evaluation-runs-dir",
        dest="evaluation_runs_dir",
        type=Path,
        default=COMPONENT_RUNS_ROOT,
        help="Directory containing standalone evaluation runs.",
    )
    parser.add_argument(
        "--checkpoint-store",
        dest="checkpoint_store",
        type=Path,
        default=DEFAULT_CHECKPOINT_STORE,
        help="Harness Checkpoint Store containing Git versions and iteration journal.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Environment file used when assembling Harness topology.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    serve(
        host=args.host,
        port=args.port,
        student_runs_dir=args.student_runs_dir,
        evaluation_runs_dir=args.evaluation_runs_dir,
        checkpoint_store=args.checkpoint_store,
        env_file=args.env_file,
    )


if __name__ == "__main__":
    main()
