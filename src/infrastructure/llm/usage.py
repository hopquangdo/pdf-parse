"""Per-call LLM usage and cost logging: tokens in / cached / out, USD, VND and latency.

Every call is logged as one line and appended to a JSONL file, and can be summed per scope (a job id).
Cost comes from the provider when it reports one (OpenRouter does); otherwise from PRICING; otherwise it is
reported as n/a rather than guessed.
"""
import contextvars
import json
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from src import config

log = logging.getLogger("llm.usage")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False

# USD per million tokens: (input, cached input, output). A None cached price bills cached tokens as normal input.
PRICING: Dict[str, Tuple[float, Optional[float], float]] = {
    "deepseek/deepseek-v4.1-flash": (0.02, None, 1.0),
    "deepseek/deepseek-v4-flash-vision-exp": (0.2156, None, 0.6468),
}

_scope: contextvars.ContextVar[str] = contextvars.ContextVar("llm_usage_scope", default="")


def abbr(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


@dataclass
class CallUsage:
    ts: float
    scope: str
    model: str
    label: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    seconds: float
    cost_usd: Optional[float]
    cost_vnd: Optional[int]
    cost_source: str  # provider | table | unknown

    def line(self) -> str:
        cost = f"${self.cost_usd:.5f} {self.cost_vnd}đ" if self.cost_usd is not None else "cost=n/a"
        where = f"{self.scope} " if self.scope else ""
        return (f"llm {where}{self.model} {self.label} in={abbr(self.input_tokens)} cache={abbr(self.cached_tokens)} "
                f"out={abbr(self.output_tokens)} {cost} {self.seconds:.1f}s")


class UsageLogger:
    def __init__(self, sink: Optional[Path] = None, usd_vnd: Optional[float] = None, pricing=None):
        self.sink = Path(sink) if sink else None
        self.usd_vnd = usd_vnd if usd_vnd is not None else config.USD_VND
        self.pricing = PRICING if pricing is None else pricing
        self._calls: List[CallUsage] = []
        self._lock = threading.Lock()
        self.listeners: List = []  # callables(CallUsage), e.g. RunLog.record_call

    def _cost(self, model: str, tokens_in: int, cached: int, tokens_out: int, provider: Optional[float]):
        if provider is not None:
            return provider, "provider"
        price = self.pricing.get(model)
        if price is None:
            return None, "unknown"
        p_in, p_cached, p_out = price
        usd = ((tokens_in - cached) * p_in + cached * (p_in if p_cached is None else p_cached) + tokens_out * p_out) / 1e6
        return usd, "table"

    def record(self, *, model: str, label: str = "", input_tokens: int = 0, cached_tokens: int = 0,
               output_tokens: int = 0, seconds: float = 0.0, provider_cost_usd: Optional[float] = None) -> CallUsage:
        usd, source = self._cost(model, input_tokens, cached_tokens, output_tokens, provider_cost_usd)
        call = CallUsage(time.time(), _scope.get(), model, label, input_tokens, cached_tokens, output_tokens, seconds,
                         usd, None if usd is None else round(usd * self.usd_vnd), source)
        with self._lock:
            self._calls.append(call)
            if self.sink:
                try:
                    self.sink.parent.mkdir(parents=True, exist_ok=True)
                    with self.sink.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(asdict(call), ensure_ascii=False) + "\n")
                except OSError:
                    log.warning("could not write the usage log to %s", self.sink)
        log.info(call.line())
        for fn in list(self.listeners):
            try:
                fn(call)
            except Exception:  # noqa: BLE001 - a logging failure must never fail the model call
                log.exception("usage listener failed")
        return call

    def totals(self, scope: str) -> Dict:
        with self._lock:
            calls = [c for c in self._calls if c.scope == scope]
        priced = [c for c in calls if c.cost_usd is not None]
        usd = sum(c.cost_usd for c in priced)  # type: ignore[misc]
        return {
            "calls": len(calls),
            "input_tokens": sum(c.input_tokens for c in calls),
            "cached_tokens": sum(c.cached_tokens for c in calls),
            "output_tokens": sum(c.output_tokens for c in calls),
            "cost_usd": round(usd, 6),
            "cost_vnd": round(usd * self.usd_vnd),
            "unpriced_calls": len(calls) - len(priced),
            "call_seconds": round(sum(c.seconds for c in calls), 2),
        }

    @staticmethod
    def format_totals(t: Dict) -> str:
        extra = f" ({t['unpriced_calls']} unpriced)" if t.get("unpriced_calls") else ""
        wall = f" wall={t['wall_seconds']:.1f}s" if "wall_seconds" in t else ""
        return (f"calls={t['calls']} in={abbr(t['input_tokens'])} cache={abbr(t['cached_tokens'])} "
                f"out={abbr(t['output_tokens'])} ${t['cost_usd']:.5f} {t['cost_vnd']}đ{extra}{wall}")

    @contextmanager
    def scope(self, name: str) -> Iterator[None]:
        token = _scope.set(name)
        try:
            yield
        finally:
            _scope.reset(token)

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()


_default: Optional[UsageLogger] = None


def get_usage_logger() -> UsageLogger:
    global _default
    if _default is None:
        _default = UsageLogger(sink=config.DATA_DIR / "logs" / "llm_usage.jsonl")
    return _default
