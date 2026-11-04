"""Reader giả cho test: trả sẵn theo nhãn vùng, hoặc theo thứ tự gọi nếu không có nhãn."""
import threading
import time
from typing import Dict, List, Optional


class FakeReader:
    def __init__(self, per_call: Optional[List[List[dict]]] = None, by_label: Optional[Dict[str, object]] = None,
                 delay: float = 0.0):
        self.per_call, self.by_label, self.delay = list(per_call or []), by_label or {}, delay
        self.calls, self._lock = [], threading.Lock()
        self.active = self.max_active = 0

    def read(self, image_png: bytes, label: str) -> List[dict]:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            return self._answer(label)
        finally:
            with self._lock:
                self.active -= 1

    def _answer(self, label: str) -> List[dict]:
        with self._lock:
            self.calls.append(label)
            if label in self.by_label:
                v = self.by_label[label]
                if isinstance(v, Exception):
                    raise v
                return v
            return self.per_call.pop(0) if self.per_call else []
