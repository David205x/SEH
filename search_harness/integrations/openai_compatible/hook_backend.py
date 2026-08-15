"""Lazy environment-backed model profiles available to registered hooks."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from search_harness.framework import HookModelRequest, HookModelResponse

from .model import OpenAICompatibleConfig, OpenAICompatibleModel


class ProfiledHookModelBackend:
    """Resolve approved model aliases without exposing endpoints to Components."""

    def __init__(
        self,
        *,
        env_file: Path | None,
        allowed_profiles: frozenset[str] = frozenset({"student"}),
        seed: int | None = None,
    ) -> None:
        self._env_file = env_file
        self._allowed_profiles = frozenset(
            profile.strip().casefold() for profile in allowed_profiles
        )
        self._models: dict[tuple[str, str | None], OpenAICompatibleModel] = {}
        self._seed = seed

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        if request.profile not in self._allowed_profiles:
            raise PermissionError(
                f"hook model profile is not enabled: {request.profile}"
            )
        model_key = (request.profile, request.thinking_mode)
        model = self._models.get(model_key)
        if model is None:
            config = OpenAICompatibleConfig.from_env(
                env_file=self._env_file, prefix=request.profile.upper()
            )
            if self._seed is not None:
                config = replace(config, seed=self._seed)
            if request.thinking_mode is not None:
                config = config.with_thinking_mode(request.thinking_mode)
            model = OpenAICompatibleModel(config)
            self._models[model_key] = model
        response = model.generate(request.model_input)
        metadata = dict(response.metadata)
        if response.usage:
            metadata["usage"] = dict(response.usage)
        return HookModelResponse(
            raw_output=response.raw_output,
            metadata=metadata,
        )
