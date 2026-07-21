from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from search_harness.adapter.__main__ import main


class AdapterCliTest(TestCase):
    def test_dispatches_critic_arguments(self) -> None:
        """Verifies the dispatches critic arguments contract."""
        with patch("search_harness.adapter.critic.run.main") as role_main:
            main(["critic", "report", "--max-steps", "3"])

        role_main.assert_called_once_with(["report", "--max-steps", "3"])

    def test_dispatches_compiler_arguments(self) -> None:
        """Verifies the dispatches compiler arguments contract."""
        with patch("search_harness.adapter.compiler.run.main") as role_main:
            main(["compiler", "critic.json", "--proposal-index", "1"])

        role_main.assert_called_once_with(
            ["critic.json", "--proposal-index", "1"]
        )
