from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.datasets import (
    DatasetConfig,
    FilteredHotpotJsonlLoader,
    create_dataset_loader,
    dataset_path_from_env_values,
)


class DatasetLoadingTest(TestCase):
    def test_loads_filtered_hotpot_jsonl_examples(self) -> None:
        """Verifies the loads filtered hotpot jsonl examples contract."""
        with TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "supported.jsonl"
            dataset_path.write_text(
                "\n".join(
                    [
                        (
                            '{"_id":"one","question":"Q1?","answer":"A1",'
                            '"type":"bridge","level":"hard",'
                            '"supporting_facts":[["T",0]],'
                            '"_filter":{"status":"supported","confidence":"high",'
                            '"evidence":[{"title":"T","quote":"Evidence."}],'
                            '"retrieval_queries":["T"]}}'
                        ),
                        (
                            '{"_id":"two","question":"Q2?",'
                            '"_filter":{"status":"error","error_type":"RuntimeError",'
                            '"error":"Server disconnected"}}'
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            loader = FilteredHotpotJsonlLoader(dataset_path)
            examples = loader.load()

        self.assertEqual(len(examples), 2)
        self.assertEqual(examples[0].example_id, "one")
        self.assertEqual(examples[0].question, "Q1?")
        self.assertEqual(examples[0].answer, "A1")
        self.assertEqual(examples[0].metadata["filter_status"], "supported")
        self.assertEqual(examples[0].metadata["supporting_facts"], [["T", 0]])
        self.assertEqual(examples[1].answer, None)
        self.assertEqual(examples[1].metadata["filter_error_type"], "RuntimeError")

    def test_load_limit(self) -> None:
        """Verifies the load limit contract."""
        with TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "data.jsonl"
            dataset_path.write_text(
                "\n".join(
                    [
                        '{"_id":"one","question":"Q1?"}',
                        '{"_id":"two","question":"Q2?"}',
                    ]
                ),
                encoding="utf-8",
            )

            examples = FilteredHotpotJsonlLoader(dataset_path).load(limit=1)

        self.assertEqual([example.example_id for example in examples], ["one"])

    def test_derives_stable_id_from_normalized_question(self) -> None:
        """Verifies the derives stable id from normalized question contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            first.write_text(
                '{"question":"Who   wrote The Hobbit?"}\n', encoding="utf-8"
            )
            second.write_text(
                '\n'.join(
                    [
                        '{"question":"Another question?"}',
                        '{"question":"Who wrote The Hobbit?"}',
                    ]
                ),
                encoding="utf-8",
            )

            first_id = FilteredHotpotJsonlLoader(first).load()[0].example_id
            second_id = FilteredHotpotJsonlLoader(second).load()[1].example_id

        self.assertEqual(first_id, second_id)
        self.assertTrue(first_id.startswith("question_sha256:"))

    def test_can_filter_by_filter_status(self) -> None:
        """Verifies the can filter by filter status contract."""
        with TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "all_results.jsonl"
            dataset_path.write_text(
                "\n".join(
                    [
                        '{"_id":"one","question":"Q1?","_filter":{"status":"supported"}}',
                        '{"_id":"two","question":"Q2?","_filter":{"status":"rejected"}}',
                    ]
                ),
                encoding="utf-8",
            )

            examples = FilteredHotpotJsonlLoader(
                dataset_path,
                required_filter_status="supported",
            ).load()

        self.assertEqual([example.example_id for example in examples], ["one"])

    def test_rejects_invalid_jsonl_record(self) -> None:
        """Verifies the rejects invalid jsonl record contract."""
        with TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "bad.jsonl"
            dataset_path.write_text('{"_id":"one","question":"Q1?"}\nnot-json', encoding="utf-8")

            loader = FilteredHotpotJsonlLoader(dataset_path)

            with self.assertRaisesRegex(ValueError, "bad.jsonl:2: invalid JSONL record"):
                loader.load()

    def test_factory_creates_filtered_hotpot_jsonl_loader(self) -> None:
        """Verifies the factory creates filtered hotpot jsonl loader contract."""
        loader = create_dataset_loader(
            DatasetConfig(
                path=Path("supported.jsonl"),
                format_name="filtered_hotpot_jsonl",
            )
        )

        self.assertIsInstance(loader, FilteredHotpotJsonlLoader)

    def test_env_path_defaults_to_supported_jsonl_under_output_dir(self) -> None:
        """Verifies the env path defaults to supported jsonl under output dir contract."""
        path = dataset_path_from_env_values(
            {"OUTPUT_DIR": r"D:\_Project\Agent\corpus_filter\output\train"}
        )

        self.assertEqual(
            path,
            Path(r"D:\_Project\Agent\corpus_filter\output\train") / "supported.jsonl",
        )

    def test_env_path_allows_explicit_jsonl_override(self) -> None:
        """Verifies the env path allows explicit jsonl override contract."""
        path = dataset_path_from_env_values(
            {
                "OUTPUT_DIR": r"D:\_Project\Agent\corpus_filter\output\train",
                "DATASET_JSONL_PATH": r"D:\custom\subset.jsonl",
            }
        )

        self.assertEqual(path, Path(r"D:\custom\subset.jsonl"))
