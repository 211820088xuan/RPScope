"""P10 结构化结果缓存 — key 含 intent+slots+graph_mtime, 自动失效。

只缓存结构化查询结果(确定性), 不缓存 LLM 生成内容。
图文件 mtime 变化时所有旧 key 自动失效。
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


_GRAPH_PATH = Path(".cache/graph.pkl")


def _graph_mtime() -> float:
    """获取 graph.pkl 的 mtime, 用于自动失效。"""
    try:
        return _GRAPH_PATH.stat().st_mtime
    except Exception:
        return 0.0


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    size: int = 0

    def hit_rate(self) -> float:
        n = self.hits + self.misses
        return self.hits / n if n else 0.0


class QueryCache:
    def __init__(self, ttl_s: float = 3600) -> None:
        self._store: dict[str, tuple[float, dict]] = {}
        self.ttl = ttl_s
        self.stats = CacheStats()

    @staticmethod
    def _key(intent: str, slots: dict, context_code: str = "") -> str:
        """key = intent + resolved_slots + context_code + graph_mtime。

        slots 是指代消解后的(含 entity_id/stock_code, 不是原始问句)。
        graph_mtime 变化 → 所有旧 key 自动失效。
        """
        # 过滤掉 _ 开头的内部字段, 只保留实际槽位
        clean_slots = {k: v for k, v in slots.items() if not k.startswith("_")}
        slots_json = json.dumps(clean_slots, sort_keys=True, ensure_ascii=False)
        gm = _graph_mtime()
        return f"{intent}|{slots_json}|{context_code}|{gm}"

    def get(self, intent: str, slots: dict, context_code: str = "") -> dict | None:
        k = self._key(intent, slots, context_code)
        now = time.time()
        if k in self._store:
            ts, val = self._store[k]
            if now - ts < self.ttl:
                self.stats.hits += 1
                return val
            del self._store[k]
        self.stats.misses += 1
        return None

    def set(self, intent: str, slots: dict, value: dict, context_code: str = "") -> None:
        self._store[self._key(intent, slots, context_code)] = (time.time(), value)
        self.stats.size = len(self._store)

    def clear(self) -> None:
        """数据重建后主动清缓存(graph mtime 变化已自动失效, 此为兜底)。"""
        self._store.clear()
        self.stats.size = 0

    def snapshot(self) -> dict:
        return {"hits": self.stats.hits, "misses": self.stats.misses,
                "size": self.stats.size, "hit_rate": f"{self.stats.hit_rate()*100:.1f}%"}
