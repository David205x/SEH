from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from search_harness.framework import (
    ChatMessage,
    HookModelRequest,
    ModelInput,
    ModelResponse,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
    ProfiledHookModelBackend,
)


class OpenAICompatibleModelTest(TestCase):
    def test_loads_config_from_env_file(self) -> None:
        """Verifies the loads config from env file contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "STUDENT_BASE_URL=http://example.test/v1",
                        "STUDENT_API_KEY=test-key",
                        "STUDENT_MODEL_ID=test-model",
                        "MAX_TOKENS=128",
                        "REQUEST_TIMEOUT=3.5",
                        "STUDENT_TEMPERATURE=0.2",
                        "STUDENT_SEED=17",
                    ]
                ),
                encoding="utf-8",
            )

            config = OpenAICompatibleConfig.from_env(env_file=env_file)

        self.assertEqual(config.base_url, "http://example.test/v1")
        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.model_id, "test-model")
        self.assertEqual(config.max_tokens, 128)
        self.assertEqual(config.timeout, 3.5)
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.seed, 17)

    def test_loads_teacher_config_from_env_file(self) -> None:
        """Verifies the loads teacher config from env file contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "TEACHER_BASE_URL=https://api.deepseek.com",
                        "TEACHER_API_KEY=teacher-key",
                        "TEACHER_MODEL_ID=deepseek-test",
                    ]
                ),
                encoding="utf-8",
            )

            config = OpenAICompatibleConfig.from_env(
                env_file=env_file,
                prefix="TEACHER",
            )

        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.api_key, "teacher-key")
        self.assertEqual(config.model_id, "deepseek-test")

    def test_prefers_prefixed_request_timeout(self) -> None:
        """Verifies the prefers prefixed request timeout contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "STUDENT_BASE_URL=http://example.test/v1",
                        "STUDENT_MODEL_ID=test-model",
                        "REQUEST_TIMEOUT=3.5",
                        "STUDENT_REQUEST_TIMEOUT=42",
                    ]
                ),
                encoding="utf-8",
            )

            config = OpenAICompatibleConfig.from_env(env_file=env_file)

        self.assertEqual(config.timeout, 42)

    def test_maps_ollama_thinking_mode_from_env_file(self) -> None:
        """Verifies the maps ollama thinking mode from env file contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "STUDENT_BASE_URL=http://127.0.0.1:11434/v1",
                        "STUDENT_MODEL_ID=qwen3:8b",
                        "STUDENT_THINKING_MODE=disabled",
                    ]
                ),
                encoding="utf-8",
            )

            config = OpenAICompatibleConfig.from_env(env_file=env_file)

        self.assertFalse(config.ollama_think)
        self.assertIsNone(config.thinking_mode)

    def test_maps_deepseek_thinking_mode_from_env_file(self) -> None:
        """DeepSeek thinking mode becomes an optional request extension."""

        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "TEACHER_BASE_URL=https://api.deepseek.com",
                        "TEACHER_MODEL_ID=teacher-test",
                        "TEACHER_THINKING_MODE=disabled",
                    ]
                ),
                encoding="utf-8",
            )

            config = OpenAICompatibleConfig.from_env(
                env_file=env_file,
                prefix="TEACHER",
            )

        self.assertEqual(config.thinking_mode, "disabled")
        self.assertIsNone(config.ollama_think)

    def test_overrides_ollama_thinking_mode_for_one_hook_model(self) -> None:
        config = OpenAICompatibleConfig(
            base_url="http://127.0.0.1:11434/v1",
            model_id="qwen3:8b",
            ollama_think=True,
        )

        overridden = config.with_thinking_mode("disabled")

        self.assertFalse(overridden.ollama_think)
        self.assertIsNone(overridden.thinking_mode)
        self.assertEqual(overridden.configured_thinking_mode, "disabled")
        self.assertTrue(overridden.supports_thinking_mode)

    def test_overrides_deepseek_thinking_mode_for_one_hook_model(self) -> None:
        config = OpenAICompatibleConfig(
            base_url="https://api.deepseek.com",
            model_id="deepseek-test",
            thinking_mode="enabled",
        )

        overridden = config.with_thinking_mode("disabled")

        self.assertEqual(overridden.thinking_mode, "disabled")
        self.assertIsNone(overridden.ollama_think)
        self.assertEqual(overridden.configured_thinking_mode, "disabled")
        self.assertTrue(overridden.supports_thinking_mode)

    def test_ignores_configured_thinking_mode_for_unknown_provider(self) -> None:
        config = OpenAICompatibleConfig(
            base_url="https://provider.example/v1",
            model_id="provider-test",
        )

        self.assertIs(
            config.with_configured_thinking_mode("disabled"),
            config,
        )
        self.assertIsNone(config.configured_thinking_mode)
        self.assertFalse(config.supports_thinking_mode)

    def test_rejects_thinking_override_for_unknown_provider(self) -> None:
        config = OpenAICompatibleConfig(
            base_url="https://provider.example/v1",
            model_id="provider-test",
        )

        with self.assertRaisesRegex(ValueError, "unavailable"):
            config.with_thinking_mode("disabled")

    def test_hook_backend_caches_models_by_profile_and_thinking_mode(self) -> None:
        base_config = OpenAICompatibleConfig(
            base_url="http://127.0.0.1:11434/v1",
            model_id="qwen3:8b",
        )
        model_input = ModelInput.from_messages(
            [ChatMessage(role="user", content="classify")]
        )
        with (
            patch(
                "search_harness.integrations.openai_compatible.hook_backend."
                "OpenAICompatibleConfig.from_env",
                return_value=base_config,
            ),
            patch(
                "search_harness.integrations.openai_compatible.hook_backend."
                "OpenAICompatibleModel"
            ) as model_type,
        ):
            model_type.return_value.generate.return_value = ModelResponse(
                raw_output='{"label":"positive"}'
            )
            backend = ProfiledHookModelBackend(env_file=None)

            for thinking_mode in ("enabled", "disabled", "disabled"):
                backend.generate(
                    HookModelRequest(
                        profile="student",
                        purpose="classification",
                        model_input=model_input,
                        thinking_mode=thinking_mode,
                    )
                )

        self.assertEqual(model_type.call_count, 2)
        self.assertEqual(
            [call.args[0].ollama_think for call in model_type.call_args_list],
            [True, False],
        )
        self.assertEqual(model_type.return_value.generate.call_count, 3)

    def test_does_not_send_thinking_extension_to_unknown_provider(self) -> None:
        """Unknown OpenAI-compatible endpoints receive only standard fields."""

        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "TEACHER_BASE_URL=https://provider.example/v1",
                        "TEACHER_MODEL_ID=teacher-test",
                        "TEACHER_THINKING_MODE=disabled",
                    ]
                ),
                encoding="utf-8",
            )

            config = OpenAICompatibleConfig.from_env(
                env_file=env_file,
                prefix="TEACHER",
            )

        self.assertIsNone(config.thinking_mode)
        self.assertIsNone(config.ollama_think)

    def test_posts_chat_completion_request_and_returns_text(self) -> None:
        """Verifies the posts chat completion request and returns text contract."""
        server = _ChatCompletionTestServer()
        try:
            model = OpenAICompatibleModel(
                OpenAICompatibleConfig(
                    base_url=server.base_url,
                    model_id="test-model",
                    api_key="secret",
                    max_tokens=32,
                    timeout=5,
                    temperature=0.1,
                )
            )

            response = model.generate(
                ModelInput.from_messages(
                    [
                        ChatMessage(role="system", content="You are concise."),
                        ChatMessage(role="user", content="hello"),
                    ]
                )
            )
        finally:
            server.close()

        self.assertEqual(response.raw_output, "<final_answer>world</final_answer>")
        self.assertEqual(server.paths, ["/v1/chat/completions"])
        self.assertEqual(server.auth_headers, ["Bearer secret"])
        self.assertEqual(
            server.requests,
            [
                {
                    "model": "test-model",
                    "messages": [
                        {"role": "system", "content": "You are concise."},
                        {"role": "user", "content": "hello"},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 32,
                }
            ],
        )

    def test_posts_ollama_reasoning_effort_when_disabled(self) -> None:
        """Ollama's OpenAI endpoint disables thinking with reasoning_effort."""
        server = _ChatCompletionTestServer()
        try:
            model = OpenAICompatibleModel(
                OpenAICompatibleConfig(
                    base_url=server.base_url,
                    model_id="test-model",
                    max_tokens=32,
                    timeout=5,
                    temperature=0.1,
                    ollama_think=False,
                )
            )

            model.generate(
                ModelInput.from_messages(
                    [ChatMessage(role="user", content="hello")]
                )
            )
        finally:
            server.close()

        self.assertEqual(server.requests[0]["reasoning_effort"], "none")
        self.assertNotIn("think", server.requests[0])

    def test_omits_ollama_reasoning_effort_when_enabled(self) -> None:
        """Enabled thinking uses the Ollama model's default reasoning mode."""

        server = _ChatCompletionTestServer()
        try:
            model = OpenAICompatibleModel(
                OpenAICompatibleConfig(
                    base_url=server.base_url,
                    model_id="test-model",
                    ollama_think=True,
                )
            )

            model.generate(
                ModelInput.from_messages(
                    [ChatMessage(role="user", content="hello")]
                )
            )
        finally:
            server.close()

        self.assertNotIn("reasoning_effort", server.requests[0])
        self.assertNotIn("think", server.requests[0])

    def test_posts_seed_when_configured(self) -> None:
        """Verifies the posts seed when configured contract."""
        server = _ChatCompletionTestServer()
        try:
            model = OpenAICompatibleModel(
                OpenAICompatibleConfig(
                    base_url=server.base_url,
                    model_id="test-model",
                    seed=42,
                )
            )
            model.generate(ModelInput.from_messages([ChatMessage(role="user", content="hello")]))
        finally:
            server.close()

        self.assertEqual(server.requests[0]["seed"], 42)

    def test_preserves_native_reasoning_metadata(self) -> None:
        """Verifies the preserves native reasoning metadata contract."""
        server = _ChatCompletionTestServer(
            response_message={
                "role": "assistant",
                "content": "<final_answer>world</final_answer>",
                "reasoning_content": "native reasoning",
            }
        )
        try:
            model = OpenAICompatibleModel(
                OpenAICompatibleConfig(base_url=server.base_url, model_id="test-model")
            )
            response = model.generate(
                ModelInput.from_messages([ChatMessage(role="user", content="hello")])
            )
        finally:
            server.close()

        self.assertEqual(
            response.raw_output,
            "<final_answer>world</final_answer>",
        )
        self.assertEqual(
            response.metadata,
            {"reasoning_content": "native reasoning"},
        )

    def test_preserves_provider_thinking_separately_from_content(self) -> None:
        """Verifies the preserves provider thinking separately from content contract."""
        server = _ChatCompletionTestServer(
            response_message={
                "role": "assistant",
                "content": "Visible preamble.\n<final_answer>world</final_answer>",
                "thinking": "provider-native thinking",
            }
        )
        try:
            model = OpenAICompatibleModel(
                OpenAICompatibleConfig(base_url=server.base_url, model_id="test-model")
            )
            response = model.generate(
                ModelInput.from_messages([ChatMessage(role="user", content="hello")])
            )
        finally:
            server.close()

        self.assertEqual(
            response.raw_output,
            "Visible preamble.\n<final_answer>world</final_answer>",
        )
        self.assertEqual(
            response.metadata,
            {"thinking": "provider-native thinking"},
        )

    def test_returns_usage_in_model_response(self) -> None:
        """Verifies usage is returned without a last-call metadata side channel."""
        server = _ChatCompletionTestServer(
            usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
        )
        try:
            model = OpenAICompatibleModel(
                OpenAICompatibleConfig(base_url=server.base_url, model_id="test-model")
            )
            response = model.generate(
                ModelInput.from_messages([ChatMessage(role="user", content="hello")])
            )
        finally:
            server.close()

        self.assertEqual(
            response.usage,
            {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        )
        self.assertEqual(response.metadata, {})


class _ChatCompletionTestServer:
    def __init__(
        self,
        response_message: dict[str, object] | None = None,
        usage: dict[str, object] | None = None,
    ) -> None:
        self.paths: list[str] = []
        self.auth_headers: list[str | None] = []
        self.requests: list[dict[str, object]] = []
        self.response_message = response_message or {
            "role": "assistant",
            "content": "<final_answer>world</final_answer>",
        }
        self.usage = dict(usage or {})

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                outer.paths.append(self.path)
                outer.auth_headers.append(self.headers.get("Authorization"))
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length).decode("utf-8")
                outer.requests.append(json.loads(raw_body))

                response = {
                    "choices": [
                        {
                            "message": outer.response_message
                        }
                    ]
                }
                if outer.usage:
                    response["usage"] = outer.usage
                body = json.dumps(response, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
