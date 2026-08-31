"""T3: 槽位抽取 — LLM 从问句中抽取槽位, 输出严格 JSON。

与意图分类 uncertain 时合并为一次 LLM 调用。
"""
from __future__ import annotations
import json, re
from src.llm.client import LLMClient

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
    prompt = (
        f"从用户问题中抽取查询槽位, 输出严格JSON(不要markdown围栏)。\n"
        f"意图: {intent}\n"
        f"槽位schema: {json.dumps(schema, ensure_ascii=False)}\n"
        f"问题: {question}\n"
        f"规则: 6位数字=股票代码; 人名直接用中文; 只输出问题里明确出现的槽位, 不要编造。"
    )
    try:
        result = llm.chat_json(
            [{"role": "system", "content": "你是槽位抽取器, 只输出JSON, 不输出任何解释。"},
             {"role": "user", "content": prompt}],
            schema_keys=list(schema.keys()),
        )
        # 清理: 去掉值为 null/空 的可选槽位
        slots = {k: v for k, v in result.items() if v is not None and v != ""}
        return {"intent": intent, "slots": slots, "raw": result}
    except Exception as e:
        return {"intent": intent, "slots": {}, "raw": {}, "error": str(e)}


def classify_and_extract(question: str, llm: LLMClient) -> dict:
    """uncertain 时合并意图分类+槽位抽取为一次 LLM 调用。"""
    prompt = (
        f"判断用户问题的意图并抽取槽位, 输出严格JSON。\n"
        f"可选意图: Q1(查关联方) Q2(两实体关系) Q3(某人控制哪些公司) "
        f"Q4(查股东/董监高/实控人) Q5(查风险事件) Q6(两公司关联方重合) Q7(其他)\n"
        f"问题: {question}\n"
        f"输出格式: {{\"intent\": \"Qx\", \"slots\": {{...}}}}\n"
        f"规则: 6位数字=股票代码; 人名用中文; 只输出问题里明确出现的槽位。"
    )
    try:
        result = llm.chat_json(
            [{"role": "system", "content": "你是意图分类+槽位抽取器, 只输出JSON。"},
             {"role": "user", "content": prompt}],
        )
        intent = result.get("intent", "Q7")
        slots = result.get("slots", {})
        slots = {k: v for k, v in slots.items() if v is not None and v != ""}
        return {"intent": intent, "slots": slots, "raw": result, "source": "llm"}
    except Exception as e:
        return {"intent": "Q7", "slots": {}, "raw": {}, "error": str(e), "source": "llm"}
