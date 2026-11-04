"""Đọc bảng thanh thép bằng VLM qua API tương thích OpenAI (OpenRouter...)."""
import base64
import json
import re
import threading
import time
from collections import Counter
from typing import Dict, List, Optional

import httpx

from src import config
from src.infrastructure.llm.usage import UsageLogger, get_usage_logger
from src.infrastructure.prompts import load_prompt
from src.infrastructure.vision.anthropic_reader import parse_rows

class TableVisionReader:
    def __init__(self, api_key: str, model: str, base_url: str = config.LLM_BASE_URL, timeout: float = 240,
                 retries: int = 3, usage_logger: UsageLogger | None = None):
        self.usage_logger = usage_logger or get_usage_logger()
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.timeout, self.retries = model, timeout, retries
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.usage: Counter = Counter()
        self._lock = threading.Lock()

    def _ask(self, png: bytes, prompt: str, label: str = "") -> str:
        b64 = base64.b64encode(png).decode()
        body = {"model": self.model, "temperature": 0, "max_tokens": 8000, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt}]}]}
        if "openrouter" in self.url:
            body["usage"] = {"include": True}  # makes OpenRouter report the real cost of the call
            body["reasoning"] = {"enabled": False}  # transcription needs no thinking; it only eats the token budget
        last: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                started = time.perf_counter()
                r = httpx.post(self.url, json=body, headers=self.headers, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                u = data.get("usage") or {}
                self.usage_logger.record(
                    model=self.model, label=label, input_tokens=u.get("prompt_tokens", 0) or 0,
                    cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0,
                    output_tokens=u.get("completion_tokens", 0) or 0, seconds=time.perf_counter() - started,
                    provider_cost_usd=u.get("cost"))
                with self._lock:
                    self.usage["calls"] += 1
                    self.usage["prompt_tokens"] += data.get("usage", {}).get("prompt_tokens", 0)
                    self.usage["completion_tokens"] += data.get("usage", {}).get("completion_tokens", 0)
                choice = data["choices"][0]
                text = choice["message"].get("content") or ""
                if not text.strip():
                    raise RuntimeError(f"model returned no answer (finish_reason={choice.get('finish_reason')})")
                return text
            except Exception as e:  # noqa: BLE001 - mạng, 429, JSON hỏng
                last = e
                time.sleep(2 ** attempt)
        raise last

    def read_table(self, png: bytes, label: str = "table") -> List[Dict]:
        return parse_rows(self._ask(png, load_prompt("table"), label))

    def read_row(self, png: bytes, label: str = "row") -> Optional[Dict]:
        rows = parse_rows(self._ask(png, load_prompt("table_row"), label))
        return rows[0] if rows else None

    def ask_json(self, png: bytes, prompt: str, label: str = ""):
        """Ask a small question about an image; the answer is a JSON object (or array)."""
        text = self._ask(png, prompt, label)
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if not m:
            raise ValueError("no JSON in the answer")
        return json.loads(m.group(0))
