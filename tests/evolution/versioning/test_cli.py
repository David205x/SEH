"""Unified root Version Store command tests."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from search_harness.cli import main
from search_harness.evolution.versioning import TemplateVersionStore

from .test_version_store import _make_template_root


class VersionStoreCliTest(unittest.TestCase):
    def test_initializes_schema_v2_store_from_root_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template_root = _make_template_root(root)
            version_store = root / "versions"
            output = io.StringIO()

            with redirect_stdout(output):
                main(
                    [
                        "version-store",
                        "init",
                        "--template-root",
                        str(template_root),
                        "--version-store",
                        str(version_store),
                        "--version-store-id",
                        "root_command_store",
                    ]
                )

            store = TemplateVersionStore(version_store)
            metadata = json.loads(
                store.metadata_file.read_text(encoding="utf-8")
            )
            versions = store.list_versions()
            store_id = store.version_store_id

        self.assertEqual(store_id, "root_command_store")
        self.assertEqual(metadata["schema_version"], 2)
        self.assertNotIn("checkpoint_store_id", metadata)
        self.assertEqual(versions[-1].version_id, "harness_v0001")
        self.assertIn("accepted version: harness_v0001", output.getvalue())


if __name__ == "__main__":
    unittest.main()
