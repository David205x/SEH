from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness._internal import parse_float, parse_int, read_env_file


class EnvTest(TestCase):
    def test_reads_utf8_env_file(self) -> None:
        """Verifies the reads utf8 env file contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        "KEY=value",
                        "QUOTED='hello world'",
                        "UNICODE=检索",
                    ]
                ),
                encoding="utf-8",
            )

            values = read_env_file(env_file)

        self.assertEqual(values["KEY"], "value")
        self.assertEqual(values["QUOTED"], "hello world")
        self.assertEqual(values["UNICODE"], "检索")

    def test_parses_positive_numbers(self) -> None:
        """Verifies the parses positive numbers contract."""
        self.assertEqual(parse_int("5", default=1, name="COUNT"), 5)
        self.assertEqual(parse_float("0.5", default=1.0, name="TEMP"), 0.5)
