"""akshare 接入层 - 带本地文件缓存、限流、重试。

铁律对应：所有外部数据接入必须有本地缓存层，禁止在开发循环中反复打真实接口。
所有网络请求带重试和限流（每秒不超过 2 次）。
报告期格式各接口不统一 -> 统一在 client 层转换。
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import threading
import time
from pathlib import Path
from typing import Any

import pandas as pd
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# 内容/编程错误：不重试，立即失败（区分网络瞬时错误）
_CONTENT_ERRORS = (KeyError, AttributeError, ValueError, TypeError, IndexError, FileNotFoundError)

CACHE_DIR = Path(os.getenv("RPSCOPE_CACHE_DIR", ".cache"))
RATE_LIMIT_RPS = float(os.getenv("RPSCOPE_RATE_LIMIT_RPS", "2.0"))


class RateLimiter:
    """简单的线程安全令牌桶式限流：保证两次调用间最小间隔。"""

    def __init__(self, rps: float) -> None:
        self.min_interval = 1.0 / rps if rps > 0 else 0.0
        self._lock = threading.Lock()
        self._last = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


class AkshareClient:
    """akshare 函数的统一缓存+限流+重试封装。

    用法：
        client = AkshareClient()
        df = client.get("stock_info_a_code_name")
        df = client.get("stock_gdfx_free_holding_detail_em", date="20260630")
    """

    _limiter = RateLimiter(RATE_LIMIT_RPS)

    def __init__(self, cache_dir: Path | str = CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- 缓存键 ----
    @staticmethod
    def _key(fn_name: str, params: dict[str, Any]) -> str:
        raw = json.dumps({"fn": fn_name, "params": params}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def _cache_path(self, fn_name: str, key: str) -> Path:
        d = self.cache_dir / fn_name
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{key}.pkl"

    @staticmethod
    def _save(path: Path, obj: Any) -> None:
        with open(path, "wb") as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _load(path: Path) -> Any:
        with open(path, "rb") as f:
            return pickle.load(f)

    # ---- 调用 ----
    def get(self, fn_name: str, **params: Any) -> pd.DataFrame:
        """获取 DataFrame，命中缓存不打网络。"""
        key = self._key(fn_name, params)
        path = self._cache_path(fn_name, key)
        if path.exists():
            return self._load(path)

        df = self._call_with_retry(fn_name, params)
        if isinstance(df, pd.DataFrame):
            self._save(path, df)
        else:
            # akshare 偶尔返回 list/dict，统一包成 DataFrame
            try:
                df = pd.DataFrame(df)
                self._save(path, df)
            except Exception:
                self._save(path.with_suffix(".raw"), df)
        return df

    @retry(
        retry=retry_if_not_exception_type(_CONTENT_ERRORS),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def _call_with_retry(self, fn_name: str, params: dict[str, Any]) -> Any:
        import akshare as ak

        fn = getattr(ak, fn_name, None)
        if fn is None:
            raise AttributeError(f"akshare 无此接口: {fn_name}")
        self._limiter.acquire()
        return fn(**params)

    # ---- 报告期归一化 ----
    @staticmethod
    def normalize_period(period: str | int | None) -> str | None:
        """统一报告期为 'YYYY-MM-DD'。处理 20260630 / 2026-06-30 / 2026Q2 等。"""
        if period is None:
            return None
        s = str(period).strip()
        # 纯数字 8 位 -> 20260630
        if s.isdigit() and len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        # 已是 ISO
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        # Q1..Q4
        if "Q" in s.upper() and len(s) >= 5:
            year = s[:4]
            q = int(s.upper().split("Q")[1])
            md = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}.get(q)
            if md:
                return f"{year}-{md}"
        return s

    def stats(self) -> dict[str, Any]:
        """缓存统计，供 docs 用。"""
        files = list(self.cache_dir.rglob("*.pkl"))
        return {
            "cache_files": len(files),
            "cache_size_kb": sum(f.stat().st_size for f in files) // 1024,
        }
