"""GLM 统一封装 - 重试/JSON修复/成本计数/可关闭开关。

通过 DashScope OpenAI 兼容端点调 glm-5.2 (从 opencode 配置取的 key)。
LLM 仅用于: 消歧兜底 / 事件抽取 / 报告撰写。判定逻辑绝不调用。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from openai import OpenAI
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_CONTENT_ERRORS = (TypeError, ValueError, KeyError, AttributeError, IndexError, FileNotFoundError)


def _load_env() -> None:
    p = Path(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

ENABLED = os.getenv("RPSCOPE_LLM_ENABLED", "true").lower() == "true"
API_KEY = os.getenv("GLM_API_KEY", "")
BASE_URL = os.getenv("GLM_BASE_URL", "")
MODEL = os.getenv("GLM_MODEL", "glm-5.2")

_metrics = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "errors": 0,
            "json_repairs": 0, "fallbacks": 0}


def metrics() -> dict[str, int]:
    return dict(_metrics)


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t
        if t.startswith(("json", "JSON")):
            t = t[4:]
        t = t.strip("`").strip()
    return t


class LLMClient:
    def __init__(self, model: str | None = None) -> None:
        self.enabled = ENABLED and bool(API_KEY) and bool(BASE_URL)
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=90.0) if self.enabled else None
        self.model = model or MODEL

    @retry(
        retry=retry_if_not_exception_type(_CONTENT_ERRORS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _raw_chat(self, messages: list[dict], temperature: float = 0.0,
                  json_mode: bool = False) -> str:
        kwargs: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        _metrics["calls"] += 1
        try:
            u = resp.usage
            _metrics["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
            _metrics["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
        except Exception:
            pass
        return resp.choices[0].message.content or ""

    def chat_stream(self, messages: list[dict], temperature: float = 0.0):
        """流式 chat, yield token chunks。"""
        if not self.enabled:
            raise RuntimeError("LLM disabled")
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, stream=True)
        for chunk in resp:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        if not self.enabled:
            raise RuntimeError("LLM disabled (RPSCOPE_LLM_ENABLED=false 或无 key")
        t0 = time.perf_counter()
        try:
            r = self._raw_chat(messages, temperature, json_mode=False)
            return r
        except Exception:
            _metrics["errors"] += 1
            raise
        finally:
            _metrics.setdefault("last_elapsed_s", round(time.perf_counter() - t0, 3))
            try:
                from src.serve.observability import log_llm_call
                log_llm_call(str(messages), time.perf_counter() - t0,
                             _metrics["prompt_tokens"] + _metrics["completion_tokens"])
            except Exception:
                pass

    def chat_json(self, messages: list[dict], schema_keys: list[str] | None = None,
                  temperature: float = 0.0) -> dict:
        """要求 JSON 输出。自动去 markdown 围栏；schema 校验失败追加提示重试一次。"""
        if not self.enabled:
            raise RuntimeError("LLM disabled")
        try:
            raw = self._raw_chat(messages, temperature, json_mode=True)
        except Exception:
            # 降级: 关 json_mode, 改用 prompt 指令
            _metrics["fallbacks"] += 1
            from src.llm.prompts import get_prompt
            raw = self._raw_chat(messages + [{"role": "system", "content": get_prompt("json_repair")[0]["content"]}],
                                 temperature, json_mode=False)
        text = _strip_fence(raw)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            _metrics["json_repairs"] += 1
            obj = json.loads(_strip_fence(raw + "}"))  # 截断修复尝试
        if schema_keys:
            missing = [k for k in schema_keys if k not in obj]
            if missing:
                _metrics["json_repairs"] += 1
                from src.llm.prompts import get_prompt
                fix = self._raw_chat(
                    messages + [{"role": "user",
                                 "content": get_prompt("schema_repair", missing=missing)[0]["content"]}],
                    temperature, json_mode=True)
                obj = json.loads(_strip_fence(fix))
        return obj
