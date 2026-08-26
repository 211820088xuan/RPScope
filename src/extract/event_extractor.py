"""P6 LLM 事件抽取 - 从公告/新闻文本抽取关联交易/对外投资/处罚事件。

这是铁律2 允许 LLM 的三处之一(消歧兜底/事件抽取/报告撰写)。
输出严格 JSON + 断言回查(事件须能在原文定位) + 标 source_type=llm_extracted。
诚实: 完整规模化需公告文本管线(P4 式), 此处提供框架+小集 demo。
"""
from __future__ import annotations

import json

from src.llm.client import LLMClient
from src.normalize.name import normalize_name

EVENT_TYPES = {"related_txn", "investment", "penalty", "guarantee", "lawsuit", "other"}


def extract_events(text: str, client: LLMClient, source_url: str = "",
                   page: int | None = None) -> list[dict]:
    """从公告文本抽取结构化事件。每事件 {event_type, counterparty, amount, summary, event_date}。"""
    if not text.strip() or not client.enabled:
        return []
    full = text[:6000]
    prompt = (
        "从下面上市公司公告文本里, 抽取事件(关联交易/对外投资/处罚/担保/诉讼等)。\n"
        "只抽明确出现的事件, 不要臆造, 数字/日期/对手方必须来自原文。\n"
        '输出 JSON: {"events":[{"event_type":"related_txn|investment|penalty|guarantee|lawsuit|other",'
        '"counterparty":"对手方名称","amount":数字或null,"summary":"一句话描述","event_date":"YYYY-MM-DD或空"}]}\n\n'
        f"公告文本:\n{full}"
    )
    try:
        obj = client.chat_json([{"role": "user", "content": prompt}], schema_keys=["events"])
        raw = obj.get("events", [])
    except Exception:
        return []
    out = []
    for e in raw:
        et = str(e.get("event_type", "other"))
        if et not in EVENT_TYPES:
            et = "other"
        cp = str(e.get("counterparty", "")).strip()
        # 断言回查: 对手方(归一化)须在原文出现, 否则丢弃(防幻觉)
        if cp and normalize_name(cp) not in normalize_name(full) and cp not in full:
            continue
        out.append({
            "event_type": et, "counterparty": cp or None,
            "amount": _num(e.get("amount")), "summary": str(e.get("summary", ""))[:200],
            "event_date": str(e.get("event_date", ""))[:10] or None,
            "source_url": source_url, "source_page": page, "source_type": "llm_extracted",
        })
    return out


def _num(v) -> float | None:
    try:
        import math
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None
