"""P10 语义缓存 - 归一化问题 + 结果缓存, 带命中率统计。

简化版(无 embedding): 问题归一化(去空格/小写/代码补齐)作 key; 同 key 命中。
生产可换 embedding 相似度阈值, 此处结构就绪。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


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
    def _key(question: str, context_code: str = "") -> str:
        # 归一化: 去多余空白, 小写; 含 context_code 避免多轮误命中
        q = re.sub(r"\s+", "", question).lower()
        return f"{q}|{context_code}"

    def get(self, question: str, context_code: str = "") -> dict | None:
        k = self._key(question, context_code)
        now = time.time()
        if k in self._store:
            ts, val = self._store[k]
            if now - ts < self.ttl:
                self.stats.hits += 1
                return val
            del self._store[k]
        self.stats.misses += 1
        return None

    def set(self, question: str, value: dict, context_code: str = "") -> None:
        self._store[self._key(question, context_code)] = (time.time(), value)
        self.stats.size = len(self._store)

    def clear(self) -> None:
        """数据重建后主动清缓存。"""
        self._store.clear()
        self.stats.size = 0

    def snapshot(self) -> dict:
        return {"hits": self.stats.hits, "misses": self.stats.misses,
                "size": self.stats.size, "hit_rate": f"{self.stats.hit_rate()*100:.1f}%"}
