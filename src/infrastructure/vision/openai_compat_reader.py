"""Đọc ảnh qua API tương thích OpenAI (OpenRouter, DeepSeek...). Model PHẢI hỗ trợ ảnh."""
import base64
import time
from typing import List

import httpx

from src import config
from src.infrastructure.llm.usage import get_usage_logger
from src.infrastructure.prompts import render_prompt
from src.infrastructure.vision.anthropic_reader import parse_rows


class OpenAICompatReader:
    def __init__(self, api_key: str, base_url: str = config.LLM_BASE_URL, model: str = config.LLM_MODEL_NAME,
                 timeout: float = 180):
        if not model:
            raise ValueError("Thiếu LLM_MODEL_NAME")
        self.url, self.model, self.timeout = base_url.rstrip("/") + "/chat/completions", model, timeout
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def read(self, image_png: bytes, label: str) -> List[dict]:
        b64 = base64.b64encode(image_png).decode()
        body = {"model": self.model, "temperature": 0, "max_tokens": 8000,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": render_prompt("page_region", label=label)}]}]}
        if "openrouter" in self.url:
            body["usage"] = {"include": True}
            body["reasoning"] = {"enabled": False}  # transcription needs no thinking; it only eats the token budget
        started = time.perf_counter()
        r = httpx.post(self.url, json=body, headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        u = data.get("usage") or {}
        get_usage_logger().record(
            model=self.model, label=label, input_tokens=u.get("prompt_tokens", 0) or 0,
            cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0,
            output_tokens=u.get("completion_tokens", 0) or 0, seconds=time.perf_counter() - started,
            provider_cost_usd=u.get("cost"))
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
        if not text.strip():  # reasoning used up max_tokens (finish_reason=length) or the model answered nothing
            raise RuntimeError(f"model returned no answer (finish_reason={choice.get('finish_reason')}, output_tokens={u.get('completion_tokens')})")
        return parse_rows(text)
