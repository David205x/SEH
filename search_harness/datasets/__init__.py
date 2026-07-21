"""Dataset loading abstractions."""

from .factory import (
    DATASET_FILE_ENV,
    DATASET_FILTER_STATUS_ENV,
    DATASET_FORMAT_ENV,
    DATASET_JSONL_PATH_ENV,
    DATASET_PATH_ENV,
    FILTERED_HOTPOT_JSONL,
    OUTPUT_DIR_ENV,
    SUPPORTED_DATASET_FILE,
    DatasetConfig,
    create_dataset_loader,
    dataset_path_from_env_values,
    dataset_loader_from_env,
    infer_dataset_format,
)
from .hotpot_filtered import FilteredHotpotJsonlLoader, FilteredHotpotJsonlMapper
from .identity import normalize_question, stable_example_id
from .jsonl import JsonlDatasetLoader
from .protocols import DatasetLoader, DatasetRecordMapper
from .types import DatasetExample, DatasetRecordContext

__all__ = [
    "DATASET_FORMAT_ENV",
    "DATASET_FILE_ENV",
    "DATASET_FILTER_STATUS_ENV",
    "DATASET_JSONL_PATH_ENV",
    "DATASET_PATH_ENV",
    "FILTERED_HOTPOT_JSONL",
    "OUTPUT_DIR_ENV",
    "SUPPORTED_DATASET_FILE",
    "DatasetConfig",
    "DatasetExample",
    "DatasetLoader",
    "DatasetRecordContext",
    "DatasetRecordMapper",
    "FilteredHotpotJsonlLoader",
    "FilteredHotpotJsonlMapper",
    "JsonlDatasetLoader",
    "create_dataset_loader",
    "dataset_path_from_env_values",
    "dataset_loader_from_env",
    "infer_dataset_format",
    "normalize_question",
    "stable_example_id",
]
