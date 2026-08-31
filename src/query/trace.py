"""T6: trace 埋点 — 结构化记录每个节点的输入输出。

写入 .cache/traces/ 下的 JSON 文件, 每次查询一个文件。
"""
from __future__ import annotations
import json, time, hashlib
from pathlib import Path

_TRACE_DIR = Path(".cache/traces")
_TRACE_DIR.mkdir(parents=True, exist_ok=True)


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

    def add_event(self, node: str, data: dict):
        self.events.append({"node": node, "elapsed_ms": round((time.perf_counter() - self.t0) * 1000, 1), **data})

    def add_llm_call(self, purpose: str, elapsed_ms: float, tokens: int = 0, retried: bool = False):
        self.llm_calls.append({"purpose": purpose, "elapsed_ms": round(elapsed_ms, 1),
                               "tokens": tokens, "retried": retried})

    def save(self) -> str:
        qid = hashlib.md5(f"{self.question}{time.time()}".encode()).hexdigest()[:8]
        path = _TRACE_DIR / f"{qid}.json"
        doc = {
            "question": self.question,
            "intent": self.intent,
            "confidence": self.confidence,
            "uncertain": self.uncertain,
            "classification_source": self.classification_source,
            "llm_calls": self.llm_calls,
            "slots": self.slots,
            "entity_links": self.entity_links,
            "template_id": self.template_id,
            "query_params": self.query_params,
            "generated_query": self.generated_query,
            "validation": self.validation,
            "query_result_count": self.query_result_count,
            "query_elapsed_ms": round(self.query_elapsed_ms, 1),
            "answer": self.answer[:500],
            "verify_result": self.verify_result,
            "events": self.events,
            "total_elapsed_ms": round((time.perf_counter() - self.t0) * 1000, 1),
        }
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
