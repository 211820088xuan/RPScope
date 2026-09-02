"""T3: 槽位抽取 — LLM 从问句中抽取槽位, 输出严格 JSON。

与意图分类 uncertain 时合并为一次 LLM 调用。
"""
from __future__ import annotations
import json, re
from src.llm.client import LLMClient
from src.llm.prompts import get_prompt

# 意图 → 槽位 schema (供 LLM 参考)
_SLOT_SCHEMA = {
    "Q1": {"company": "stock_code", "rule_ids?": "list of R1-R7", "min_confidence?": "high/medium/low", "as_of?": "date"},
    "Q2": {"entity_a": "公司名/代码或人名", "entity_b": "公司名/代码或人名", "max_hops?": "int", "as_of?": "date"},
    "Q3": {"entity": "人名/机构名", "relation_type?": "control/hold/serve", "min_ratio?": "float", "as_of?": "date"},
    "Q4": {"company": "stock_code", "role_type": "holder/controller/director/all", "top_n?": "int", "as_of?": "date"},
    "Q5": {"company": "stock_code", "event_types?": "list of guarantee/lawsuit/pledge/related_txn", "date_range?": "[start,end]"},
    "Q6": {"company_a": "stock_code", "company_b": "stock_code", "as_of?": "date"},
    "Q7": {},
}


def extract_slots(question: str, intent: str, llm: LLMClient) -> dict:
    """LLM 从问句中抽取槽位, 返回 {intent, slots, raw}。"""
    schema = _SLOT_SCHEMA.get(intent, {})
    if not schema:
        return {"intent": intent, "slots": {}, "raw": {}}
    messages = get_prompt("slot_filling",
        intent=intent,
        schema=json.dumps(schema, ensure_ascii=False),
        question=question,
    )
    try:
        result = llm.chat_json(messages, schema_keys=list(schema.keys()))
        # 清理: 去掉值为 null/空 的可选槽位
        slots = {k: v for k, v in result.items() if v is not None and v != ""}
        return {"intent": intent, "slots": slots, "raw": result}
    except Exception as e:
        return {"intent": intent, "slots": {}, "raw": {}, "error": str(e)}


def classify_and_extract(question: str, llm: LLMClient) -> dict:
    """uncertain 时合并意图分类+槽位抽取为一次 LLM 调用。"""
    messages = get_prompt("intent_classify", question=question)
    try:
        result = llm.chat_json(messages)
        intent = result.get("intent", "Q7")
        slots = result.get("slots", {})
        slots = {k: v for k, v in slots.items() if v is not None and v != ""}
        return {"intent": intent, "slots": slots, "raw": result, "source": "llm"}
    except Exception as e:
        return {"intent": "Q7", "slots": {}, "raw": {}, "error": str(e), "source": "llm"}
