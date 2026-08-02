"""Dataset loader factory used by runners."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from search_harness._internal import get_env_value, read_env_file

from .hotpot_filtered import FilteredHotpotJsonlLoader
from .protocols import DatasetLoader


DATASET_FORMAT_ENV = "DATASET_FORMAT"
DATASET_FILE_ENV = "DATASET_FILE"
DATASET_FILTER_STATUS_ENV = "DATASET_FILTER_STATUS"
DATASET_JSONL_PATH_ENV = "DATASET_JSONL_PATH"
DATASET_PATH_ENV = "DATASET_PATH"
OUTPUT_DIR_ENV = "OUTPUT_DIR"
FILTERED_HOTPOT_JSONL = "filtered_hotpot_jsonl"
SUPPORTED_DATASET_FILE = "supported.jsonl"


@dataclass(frozen=True)
class DatasetConfig:
    """Configuration for a dataset loader."""

    path: Path
    format_name: str = FILTERED_HOTPOT_JSONL
    filter_status: str | None = None

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "DatasetConfig":
        values = read_env_file(env_file)
        path = dataset_path_from_env_values(values)
        format_name = get_env_value(values, DATASET_FORMAT_ENV)
        if format_name is None:
            format_name = infer_dataset_format(path)
        return cls(
            path=path,
            format_name=format_name,
            filter_status=get_env_value(values, DATASET_FILTER_STATUS_ENV),
        )


def infer_dataset_format(path: Path) -> str:
    if path.suffix.lower() == ".jsonl":
        return FILTERED_HOTPOT_JSONL
    raise ValueError(f"{DATASET_FORMAT_ENV} is required for dataset file: {path}")


def dataset_path_from_env_values(values: dict[str, str]) -> Path:
    raw_jsonl_path = get_env_value(values, DATASET_JSONL_PATH_ENV)
    if raw_jsonl_path is not None:
        return Path(raw_jsonl_path)

    raw_output_dir = get_env_value(values, OUTPUT_DIR_ENV)
    if raw_output_dir is not None:
        dataset_file = get_env_value(values, DATASET_FILE_ENV) or SUPPORTED_DATASET_FILE
        return Path(raw_output_dir) / dataset_file

    raw_dataset_path = get_env_value(values, DATASET_PATH_ENV)
    if raw_dataset_path is not None:
        path = Path(raw_dataset_path)
        if path.suffix.lower() == ".jsonl":
            return path

    raise ValueError(
        f"{DATASET_JSONL_PATH_ENV} or {OUTPUT_DIR_ENV} is required "
        f"for filtered JSONL dataset loading"
    )


def create_dataset_loader(config: DatasetConfig) -> DatasetLoader:
    normalized = config.format_name.strip().lower()
    if normalized == FILTERED_HOTPOT_JSONL:
        return FilteredHotpotJsonlLoader(
            config.path,
            required_filter_status=config.filter_status,
        )
    raise ValueError(f"unsupported dataset format: {config.format_name}")


def dataset_loader_from_env(env_file: Path | None = None) -> DatasetLoader:
    return create_dataset_loader(DatasetConfig.from_env(env_file=env_file))
