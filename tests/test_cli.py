"""Unified root CLI routing tests."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from search_harness.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RootCliTest(unittest.TestCase):
    def test_routes_run_arguments(self) -> None:
        with patch(
            "search_harness.runners.run_agent_once.main"
        ) as run_main:
            main(["run", "one", "question", "--show-trace"])

        run_main.assert_called_once_with(
            ["one", "question", "--show-trace"]
        )

    def test_routes_public_evolve_start_name(self) -> None:
        with patch(
            "search_harness.evolution.control.cli.main"
        ) as evolve_main:
            main(["evolve", "start", "--run-dir", "run"])

        evolve_main.assert_called_once_with(
            ["start", "--run-dir", "run"]
        )

    def test_validates_template_through_shared_assembly(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            main(
                [
                    "template",
                    "validate",
                    str(PROJECT_ROOT / "harness_templates/student/baseline"),
                ]
            )

        text = output.getvalue()
        self.assertIn("template valid:", text)
        self.assertIn("harness_id: baseline_search", text)


if __name__ == "__main__":
    unittest.main()
