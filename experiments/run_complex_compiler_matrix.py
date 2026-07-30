"""Run the complex Compiler optimization matrix with bounded parallelism."""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STUDY_ROOT = (
    PROJECT_ROOT
    / "runs"
    / "components"
    / "teacher"
    / "mechanism_compilation_validation_01"
)
COMPLEX_ROOT = STUDY_ROOT / "complex_optimization_study"
RUNTIME_ROOT = STUDY_ROOT / "runtime_optimization_study"

TEMPLATES = {
    "canonical": PROJECT_ROOT / "harness_templates" / "teacher" / "compiler" / "plugins",
    "production_prompt": (
        PROJECT_ROOT / "harness_templates" / "teacher" / "compiler" / "plugins"
    ),
    "production_prompt_v2": (
        PROJECT_ROOT / "harness_templates" / "teacher" / "compiler" / "plugins"
    ),
    "production_finalizer": (
        PROJECT_ROOT / "harness_templates" / "teacher" / "compiler" / "plugins"
    ),
    "production_packet": (
        PROJECT_ROOT / "harness_templates" / "teacher" / "compiler" / "plugins"
    ),
    "lean": STUDY_ROOT / "cost_study" / "lean_plugins",
    "mechanical": RUNTIME_ROOT / "mechanical_plugins",
    "packet": RUNTIME_ROOT / "packet_strict_plugins",
    "combined": RUNTIME_ROOT / "combined_plugins",
}
SCENARIOS = (
    "post_tool_rewrite",
    "post_prompt_context",
    "hook_model_refinement",
    "pre_final_semantic",
)


@dataclass(frozen=True)
class MatrixJob:
    """One independent Teacher Compiler invocation."""

    condition: str
    scenario: str
    replicate: int
    template_root: Path
    request_file: Path
    output_file: Path
    stdout_file: Path
    stderr_file: Path


def main() -> None:
    args = parse_args()
    jobs = _jobs(
        conditions=args.conditions,
        replicates=args.replicates,
        overwrite=args.overwrite,
    )
    if not jobs:
        print("no pending matrix jobs")
        return
    failures = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(_run_job, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            returncode = future.result()
            label = f"{job.condition}/{job.scenario}/r{job.replicate:02d}"
            print(f"{label}: exit={returncode}")
            if returncode != 0:
                failures.append(label)
    if failures:
        raise RuntimeError(f"Compiler matrix jobs failed: {failures}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=tuple(TEMPLATES),
        required=True,
    )
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.replicates < 1:
        parser.error("--replicates must be positive")
    if not 1 <= args.max_workers <= 5:
        parser.error("--max-workers must be between 1 and 5")
    return args


def _jobs(
    *,
    conditions: list[str],
    replicates: int,
    overwrite: bool,
) -> list[MatrixJob]:
    jobs = []
    for condition in conditions:
        request_name = (
            "packet_compiler_request.json"
            if condition in {"packet", "combined"}
            else "compiler_request.json"
        )
        for scenario in SCENARIOS:
            scenario_root = COMPLEX_ROOT / scenario
            output_root = scenario_root / condition
            output_root.mkdir(parents=True, exist_ok=True)
            for replicate in range(1, replicates + 1):
                output = output_root / f"compiler_run_{replicate:02d}.json"
                if output.exists() and not overwrite:
                    continue
                jobs.append(
                    MatrixJob(
                        condition=condition,
                        scenario=scenario,
                        replicate=replicate,
                        template_root=TEMPLATES[condition],
                        request_file=scenario_root / request_name,
                        output_file=output,
                        stdout_file=output_root / f"compiler_run_{replicate:02d}.stdout.log",
                        stderr_file=output_root / f"compiler_run_{replicate:02d}.stderr.log",
                    )
                )
    return jobs


def _run_job(job: MatrixJob) -> int:
    command = [
        sys.executable,
        "-m",
        "search_harness.teacher",
        "--template_root",
        str(job.template_root),
        "--request_file",
        str(job.request_file),
        "--output-file",
        str(job.output_file),
        "--env-file",
        str(PROJECT_ROOT / ".env"),
        "--max-turns",
        "30",
    ]
    with (
        job.stdout_file.open("w", encoding="utf-8") as stdout,
        job.stderr_file.open("w", encoding="utf-8") as stderr,
    ):
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    return completed.returncode


if __name__ == "__main__":
    main()
