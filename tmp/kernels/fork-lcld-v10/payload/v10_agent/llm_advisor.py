"""Local vLLM Advisor client with multimodal support and offline Mock backend."""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Mapping

from v10_agent.config import V10Config

logger = logging.getLogger(__name__)


def format_multimodal_message(text_prompt: str, image_png_bytes: bytes | None = None) -> list[dict[str, Any]]:
    """Format OpenAI-compatible chat completion user message with optional base64 image."""
    if not image_png_bytes:
        return [{"role": "user", "content": text_prompt}]

    b64_image = base64.b64encode(image_png_bytes).decode("ascii")
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                },
            ],
        }
    ]


class BaseLLMAdvisor:
    """Interface for LLM Advisor backends."""

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        config: V10Config,
        image_bytes: bytes | None = None,
        agent_role: str = "generic",
    ) -> str:
        raise NotImplementedError


class VLLMAdvisor(BaseLLMAdvisor):
    """Client for local vLLM OpenAI-compatible server (/v1/chat/completions)."""

    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1", api_key: str = "EMPTY"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        config: V10Config,
        image_bytes: bytes | None = None,
        agent_role: str = "generic",
    ) -> str:
        url = f"{self.base_url}/chat/completions"

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        user_msg = format_multimodal_message(
            user_prompt,
            image_bytes if config.qwen_multimodal_enabled else None,
        )
        messages.extend(user_msg)

        # Dynamically discover model id if not explicitly cached
        model_id = getattr(self, "_cached_model_id", None)
        if not model_id:
            try:
                models_req = urllib.request.Request(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                with urllib.request.urlopen(models_req, timeout=3) as m_resp:
                    m_data = json.loads(m_resp.read().decode("utf-8"))
                    data_list = m_data.get("data", [])
                    if data_list:
                        model_id = data_list[0].get("id")
                        self._cached_model_id = model_id
            except Exception:
                model_id = config.qwen_model_path
        if not model_id:
            model_id = config.qwen_model_path

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": config.qwen_temperature,
            "top_p": config.qwen_top_p,
            "max_tokens": config.qwen_max_output_tokens,
            "presence_penalty": config.qwen_presence_penalty,
        }

        if config.qwen_enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": True}

        # Extra sampling params supported by vLLM
        extra_body: dict[str, Any] = {}
        if config.qwen_top_k > 0:
            extra_body["top_k"] = config.qwen_top_k
        if config.qwen_repeat_penalty > 0:
            extra_body["repetition_penalty"] = config.qwen_repeat_penalty
        if extra_body:
            payload["extra_body"] = extra_body

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        timeout = config.qwen_timeout_seconds or 700
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                resp_json = json.loads(response.read().decode("utf-8"))
                choices = resp_json.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    content = str(msg.get("content") or "")
                    # If model returned pure reasoning_content and no content, fallback to reasoning
                    if not content and msg.get("reasoning_content"):
                        content = str(msg.get("reasoning_content"))
                    return content
                return ""
        except Exception as exc:
            logger.error(f"vLLM query failed for role {agent_role!r}: {exc}")
            raise


class MockLLMAdvisor(BaseLLMAdvisor):
    """Deterministic in-memory mock backend for offline testing without GPU."""

    def __init__(self) -> None:
        self.responses_by_role: dict[str, list[str]] = {
            "explorer": [],
            "coder": [],
            "solver": [],
            "generic": [],
        }
        self.call_history: list[dict[str, Any]] = []

    def set_response(self, role: str, response: str) -> None:
        self.responses_by_role.setdefault(role, []).append(response)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        config: V10Config,
        image_bytes: bytes | None = None,
        agent_role: str = "generic",
    ) -> str:
        self.call_history.append({
            "role": agent_role,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "has_image": image_bytes is not None,
        })
        queue = self.responses_by_role.get(agent_role, [])
        if queue:
            return queue.pop(0)
        default_queue = self.responses_by_role.get("generic", [])
        if default_queue:
            return default_queue.pop(0)
        return "{}"


def build_llm_advisor(config: V10Config) -> BaseLLMAdvisor:
    """Factory creating appropriate advisor backend based on configuration."""
    if config.llm_advisor_backend == "fake":
        return MockLLMAdvisor()
    return VLLMAdvisor(
        base_url=config.qwen_vllm_base_url,
        api_key=config.qwen_vllm_api_key,
    )
