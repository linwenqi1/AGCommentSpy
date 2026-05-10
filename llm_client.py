from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request




def _build_chat_completions_url(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    parsed = parse.urlparse(cleaned)

    if cleaned.endswith("/chat/completions"):
        return cleaned
    if parsed.path in ("", "/"):
        return f"{cleaned}/v1/chat/completions"
    return f"{cleaned}/chat/completions"



@dataclass
class ChatCompletionResult:
    content: str
    raw_response: dict[str, Any]


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "").strip()
        self.api_key = api_key or os.getenv("LLM_API_KEY", "").strip()
        self.model = model or os.getenv("LLM_MODEL", "").strip()
        self.timeout = timeout

        if not self.base_url:
            raise ValueError("LLM_BASE_URL is required")
        if not self.api_key:
            raise ValueError("LLM_API_KEY is required")
        if not self.model:
            raise ValueError("LLM_MODEL is required")

        self.chat_completions_url = _build_chat_completions_url(self.base_url)

    def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> ChatCompletionResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            raw_response = self._post_json(payload)
        except RuntimeError as exc:
            if "response_format" not in str(exc):
                raise
            fallback_payload = dict(payload)
            fallback_payload.pop("response_format", None)
            raw_response = self._post_json(fallback_payload)
        content = self._extract_message_content(raw_response)
        return ChatCompletionResult(content=content, raw_response=raw_response)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        req = request.Request(
            self.chat_completions_url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                response_bytes = resp.read()
        except error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"LLM request failed with status {exc.code}: {response_text}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

        try:
            data = json.loads(response_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM response is not valid JSON") from exc

        if "error" in data:
            raise RuntimeError(f"LLM API returned error: {data['error']}")

        return data

    @staticmethod
    def _extract_message_content(response_data: dict[str, Any]) -> str:
        choices = response_data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM response does not contain choices")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise RuntimeError("LLM response choice is invalid")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("LLM response message is invalid")

        content = message.get("content")
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_value = item.get("text", "")
                    if isinstance(text_value, str):
                        text_parts.append(text_value)
            if text_parts:
                return "\n".join(text_parts)

        raise RuntimeError("LLM response content is empty")
