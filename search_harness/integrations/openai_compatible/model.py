"""OpenAI-compatible Chat Completions Model 集成。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import parse as urllib_parse
from urllib import error as urllib_error
from urllib import request as urllib_request

from search_harness.framework.agent import ModelInput, ModelResponse
from search_harness._internal import (
    get_env_value,
    parse_float,
    parse_int,
    read_env_file,
)


MAX_TOKENS_ENV = "MAX_TOKENS"
REQUEST_TIMEOUT_ENV = "REQUEST_TIMEOUT"


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    """Configuration for a text-only OpenAI-compatible chat model."""

    base_url: str
    model_id: str
    api_key: str = ""
    max_tokens: int = 1024
    timeout: float = 60.0
    temperature: float = 0.6
    seed: int | None = None
    ollama_think: bool | None = None
    thinking_mode: str | None = None

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("model base_url must not be empty")
        if not self.model_id.strip():
            raise ValueError("model model_id must not be empty")
        if self.max_tokens < 1:
            raise ValueError("model max_tokens must be positive")
        if self.timeout <= 0:
            raise ValueError("model timeout must be positive")
        if self.thinking_mode not in {None, "enabled", "disabled"}:
            raise ValueError("thinking_mode must be enabled, disabled, or None")

    @classmethod
    def from_env(
        cls,
        env_file: Path | None = None,
        prefix: str = "STUDENT",
    ) -> "OpenAICompatibleConfig":
        """Load model settings from process environment and .env."""

        values = read_env_file(env_file)
        normalized_prefix = prefix.strip().upper()
        if not normalized_prefix:
            raise ValueError("model env prefix must not be empty")

        base_url_env = _env_name(normalized_prefix, "BASE_URL")
        api_key_env = _env_name(normalized_prefix, "API_KEY")
        model_id_env = _env_name(normalized_prefix, "MODEL_ID")
        timeout_env = _env_name(normalized_prefix, "REQUEST_TIMEOUT")
        max_tokens_env = _env_name(normalized_prefix, "MAX_TOKENS")
        temperature_env = _env_name(normalized_prefix, "TEMPERATURE")
        thinking_mode_env = _env_name(normalized_prefix, "THINKING_MODE")
        seed_env = _env_name(normalized_prefix, "SEED")

        base_url = get_env_value(values, base_url_env)
        model_id = get_env_value(values, model_id_env)
        if base_url is None:
            raise ValueError(f"{base_url_env} is required")
        if model_id is None:
            raise ValueError(f"{model_id_env} is required")

        max_tokens_value = get_env_value(values, max_tokens_env)
        max_tokens_name = max_tokens_env
        if max_tokens_value is None:
            max_tokens_value = get_env_value(values, MAX_TOKENS_ENV)
            max_tokens_name = MAX_TOKENS_ENV
        max_tokens = parse_int(
            max_tokens_value,
            default=1024,
            name=max_tokens_name,
        )
        timeout_value = get_env_value(values, timeout_env)
        timeout_name = timeout_env
        if timeout_value is None:
            timeout_value = get_env_value(values, REQUEST_TIMEOUT_ENV)
            timeout_name = REQUEST_TIMEOUT_ENV
        timeout = parse_float(timeout_value, default=60.0, name=timeout_name)
        temperature = parse_float(
            get_env_value(values, temperature_env),
            default=0.6,
            name=temperature_env,
        )
        thinking_mode = _parse_thinking_mode(
            get_env_value(values, thinking_mode_env),
            thinking_mode_env,
        )
        ollama_think = _ollama_think(
            base_url=base_url,
            thinking_mode=thinking_mode,
        )
        return cls(
            base_url=base_url,
            model_id=model_id,
            api_key=get_env_value(values, api_key_env) or "",
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=temperature,
            seed=_parse_optional_int(get_env_value(values, seed_env), seed_env),
            ollama_think=ollama_think,
            thinking_mode=(
                thinking_mode if _is_deepseek_base_url(base_url) else None
            ),
        )

    @property
    def chat_completions_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    def provenance(self) -> dict[str, Any]:
        """Return non-secret generation settings used for one experiment."""

        return {
            "provider": "openai_compatible",
            "base_url": self.base_url,
            "model_id": self.model_id,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "temperature": self.temperature,
            "seed": self.seed,
            "ollama_think": self.ollama_think,
            "thinking_mode": self.thinking_mode,
        }


class OpenAICompatibleModel:
    """通过 OpenAI-compatible Chat Completions 调用文本模型。"""

    def __init__(self, config: OpenAICompatibleConfig) -> None:
        self.config = config
        self.requests: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []

    @classmethod
    def from_env(
        cls,
        env_file: Path | None = None,
        prefix: str = "STUDENT",
    ) -> "OpenAICompatibleModel":
        return cls(OpenAICompatibleConfig.from_env(env_file=env_file, prefix=prefix))

    def generate(self, model_input: ModelInput) -> ModelResponse:
        payload = {
            "model": self.config.model_id,
            "messages": [message.to_dict() for message in model_input.messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if self.config.ollama_think is not None:
            payload["think"] = self.config.ollama_think
        if self.config.thinking_mode is not None:
            payload["thinking"] = {"type": self.config.thinking_mode}
        if self.config.seed is not None:
            payload["seed"] = self.config.seed
        self.requests.append(json.loads(json.dumps(payload, ensure_ascii=False)))
        response = self._post_chat_completion(payload)
        self.responses.append(response)
        return ModelResponse(
            raw_output=_extract_text_response(response),
            usage=_extract_usage(response),
            metadata=_extract_response_metadata(response),
        )

    def _post_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        request = urllib_request.Request(
            self.config.chat_completions_url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc

        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("chat completion response must be a JSON object")
        return payload


def _extract_text_response(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat completion response has no choices")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("chat completion choice must be an object")

    message = first_choice.get("message")
    if isinstance(message, dict):
        content = message.get("content", "")
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    text = first_choice.get("text")
    if isinstance(text, str):
        return text

    raise ValueError("chat completion choice has no text content")


def _extract_response_metadata(response: dict[str, Any]) -> dict[str, Any]:
    """Preserve selected native reasoning fields without changing model text."""

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return {}
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return {}

    metadata: dict[str, Any] = {}
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = message.get(key)
        if isinstance(value, str) and value:
            metadata[key] = value
    return metadata


def _extract_usage(response: dict[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    return dict(usage) if isinstance(usage, dict) else {}


def _env_name(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _parse_optional_int(value: str | None, name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_thinking_mode(value: str | None, name: str) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in {"", "auto", "default"}:
        return None
    if normalized in {"disabled", "false", "off", "0", "no"}:
        return "disabled"
    elif normalized in {"enabled", "true", "on", "1", "yes"}:
        return "enabled"
    raise ValueError(f"{name} must be one of auto, disabled, or enabled")


def _ollama_think(*, base_url: str, thinking_mode: str | None) -> bool | None:
    if not _is_default_ollama_base_url(base_url) or thinking_mode is None:
        return None
    return thinking_mode == "enabled"


def _is_default_ollama_base_url(base_url: str) -> bool:
    parsed = urllib_parse.urlparse(base_url)
    return parsed.port == 11434


def _is_deepseek_base_url(base_url: str) -> bool:
    parsed = urllib_parse.urlparse(base_url)
    return (parsed.hostname or "").casefold() == "api.deepseek.com"
