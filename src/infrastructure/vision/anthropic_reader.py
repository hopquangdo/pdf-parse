"""Đọc ảnh bản vẽ bằng Claude, trả về các dòng thống kê."""
import base64
import json
import re
import time
from typing import List

from src import config
from src.infrastructure.llm.usage import get_usage_logger
from src.infrastructure.prompts import render_prompt

def parse_rows(text: str) -> List[dict]:
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else []


class AnthropicReader:
    def __init__(self, client=None, model: str = config.ANTHROPIC_MODEL):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client, self.model = client, model

    def read(self, image_png: bytes, label: str) -> List[dict]:
        started = time.perf_counter()
        msg = self.client.messages.create(
            model=self.model, max_tokens=8000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.b64encode(image_png).decode()}},
                {"type": "text", "text": render_prompt("page_region", label=label)},
            ]}])
        u = msg.usage
        cached = getattr(u, "cache_read_input_tokens", 0) or 0
        created = getattr(u, "cache_creation_input_tokens", 0) or 0
        get_usage_logger().record(model=self.model, label=label, input_tokens=u.input_tokens + cached + created,
                                  cached_tokens=cached, output_tokens=u.output_tokens, seconds=time.perf_counter() - started)
        return parse_rows("".join(b.text for b in msg.content if b.type == "text"))
