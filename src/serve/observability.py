"""P10 自建链路追踪 - 每步耗时 + LLM 调用日志(prompt hash/耗时/token/缓存命中)。

不依赖 Langfuse(需装+key), 自建轻量 trace; 接入 LLMClient + agent。
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

_traces: list[dict] = []


@dataclass
class Span:
    name: str
    elapsed: float = 0.0
    meta: dict = field(default_factory=dict)


def trace(name: str):
    """装饰器: 记录函数耗时。"""
    def deco(fn):
        def wrap(*a, **kw):
            t0 = time.perf_counter()
            r = fn(*a, **kw)
            _traces.append({"name": name, "elapsed_ms": (time.perf_counter() - t0) * 1000})
            return r
        return wrap
    return deco


def log_llm_call(prompt: str, elapsed: float, tokens: int, cached: bool = False) -> None:
    ph = hashlib.sha1(prompt.encode()).hexdigest()[:10]
    _traces.append({"name": "llm", "elapsed_ms": elapsed * 1000,
                    "prompt_hash": ph, "tokens": tokens, "cached": cached})


def snapshot() -> list[dict]:
    return list(_traces)


def clear() -> None:
    _traces.clear()
