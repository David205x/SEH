"""Research-slice experiment entrypoint tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from experiments.run_research_slice import parse_args


class ResearchSliceArgumentsTest(unittest.TestCase):
    def test_defaults_to_stopping_before_distiller(self) -> None:
        args = parse_args(["--run-dir", "runs/evolution/debug"])

        self.assertEqual(args.run_dir, Path("runs/evolution/debug"))
        self.assertEqual(args.stop_before, "distill_mechanism")

    def test_accepts_compiler_boundary(self) -> None:
        args = parse_args(
            [
                "--run-dir",
                "runs/evolution/debug",
                "--stop-before",
                "compile_candidate",
            ]
        )

        self.assertEqual(args.stop_before, "compile_candidate")


if __name__ == "__main__":
    unittest.main()
