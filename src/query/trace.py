"""T6: trace 埋点 — 结构化记录每个节点的输入输出。

写入 .cache/traces/ 下的 JSON 文件, 每次查询一个文件。
T3: 存储策略 — 单文件 answer 截断 500 字, 总量上限 500 文件, 脱敏 API key。
"""
from __future__ import annotations
import json, time, hashlib, os
from pathlib import Path

_TRACE_DIR = Path(".cache/traces")
_TRACE_DIR.mkdir(parents=True, exist_ok=True)
_MAX_TRACES = 500  # 总量上限
_MAX_ANSWER_LEN = 500  # answer 截断


def _redact(text: str) -> str:
    """脱敏: 移除可能的 API key / token。"""
    if not text:
        return text
    import re
    text = re.sub(r"sk-[a-zA-Z0-9]{10,}", "sk-***", text)
    text = re.sub(r"Bearer\s+[a-zA-Z0-9]{10,}", "Bearer ***", text)
    text = re.sub(r"api[_-]?key[=:]\s*\S+", "api_key=***", text, flags=re.IGNORECASE)
    return text


def _cleanup_old():
    """清理过期 trace 文件, 保持总量上限。"""
    files = sorted(_TRACE_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)
    for f in files[_MAX_TRACES:]:
        f.unlink(missing_ok=True)


class Trace:
    def __init__(self, question: str):
        self.question = question
        self.t0 = time.perf_counter()
        self.events: list[dict] = []
        self.intent: str = ""
        self.confidence: float = 0.0
        self.uncertain: bool = False
        self.classification_source: str = ""
        self.llm_calls: list[dict] = []
        self.slots: dict = {}
        self.entity_links: list[dict] = []
        self.template_id: str = ""
        self.query_params: dict = {}
        self.query_result_count: int = 0
        self.query_elapsed_ms: float = 0.0
        self.generated_query: str | None = None
        self.validation: dict | None = None
        self.answer: str = ""
        self.verify_result: dict | None = None
        self._coref_entity: dict | None = None  # 补埋点: 指代消解的目标实体

    def add_event(self, node: str, data: dict):
        self.events.append({"node": node, "elapsed_ms": round((time.perf_counter() - self.t0) * 1000, 1), **data})

    def add_llm_call(self, purpose: str, elapsed_ms: float, tokens: int = 0, retried: bool = False,
                     output_summary: str = "", error_type: str = ""):
        self.llm_calls.append({"purpose": purpose, "elapsed_ms": round(elapsed_ms, 1),
                               "tokens": tokens, "retried": retried,
                               "output_summary": output_summary[:200],  # 结构化输出摘要, 不含完整prompt
                               "error_type": error_type})

    def save(self) -> str:
        qid = hashlib.md5(f"{self.question}{time.time()}".encode()).hexdigest()[:8]
        path = _TRACE_DIR / f"{qid}.json"
        doc = {
            "question": _redact(self.question[:200]),
            "intent": self.intent,
            "confidence": self.confidence,
            "uncertain": self.uncertain,
            "classification_source": self.classification_source,
            "llm_calls": [{"purpose": c.get("purpose",""), "elapsed_ms": c.get("elapsed_ms",0),
                           "tokens": c.get("tokens",0), "retried": c.get("retried",False),
                           "output_summary": c.get("output_summary",""), "error_type": c.get("error_type","")}
                          for c in self.llm_calls],
            "slots": {k: v for k, v in self.slots.items() if not k.startswith("_")},
            "coreference_resolved": self._coref_entity,  # 补埋点: 指代消解结果
            "entity_links": [{"slot": k, "method": v} for k, v in self.entity_links.items() if k.startswith("_")],
            "template_id": self.template_id,
            "query_params": self.query_params,
            "generated_query": _redact(self.generated_query) if self.generated_query else None,
            "validation": self.validation,
            "query_result_count": self.query_result_count,
            "query_elapsed_ms": round(self.query_elapsed_ms, 1),
            "answer": _redact(self.answer[:_MAX_ANSWER_LEN]),
            "verify_result": self.verify_result,
            "events": self.events,
            "total_elapsed_ms": round((time.perf_counter() - self.t0) * 1000, 1),
        }
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        _cleanup_old()
        return str(path)
