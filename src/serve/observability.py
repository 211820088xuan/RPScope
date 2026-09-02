"""已废弃 — 使用 src/query/trace.py 替代。

此模块是早期轻量 trace, 仅被 LLMClient.chat() 调用(非 chat_stream/chat_json)。
trace.py 提供完整的 per-query 文件持久化 trace + 脱敏 + API 端点, 已完全覆盖此模块功能。

保留仅为向后兼容, 不再维护。新代码不应 import 此模块。
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
    """装饰器: 记录函数耗时。已废弃, 请使用 src/query/trace.py。"""
    def deco(fn):
        def wrap(*a, **kw):
            t0 = time.perf_counter()
            r = fn(*a, **kw)
            _traces.append({"name": name, "elapsed_ms": (time.perf_counter() - t0) * 1000})
            return r
        return wrap
    return deco


def log_llm_call(prompt: str, elapsed: float, tokens: int, cached: bool = False) -> None:
    """已废弃, 请使用 Trace.add_llm_call()。"""
    ph = hashlib.sha1(prompt.encode()).hexdigest()[:10]
    _traces.append({"name": "llm", "elapsed_ms": elapsed * 1000,
                    "prompt_hash": ph, "tokens": tokens, "cached": cached})


def snapshot() -> list[dict]:
    return list(_traces)


def clear() -> None:
    _traces.clear()
