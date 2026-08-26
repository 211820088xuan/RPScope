"""P7 意图路由 - 关键词/正则分类, 无 LLM(简单问题不进多跳)。

4 意图:
  fact_query      -> 直接 SQL(<500ms): 股东/高管/基本信息
  related_party   -> 规则引擎(<3s): 关联方
  relation_explain -> 定向路径(<2s): A和B什么关系
  open_qa         -> 完整 Agent(<15s): 开放问答
"""
from __future__ import annotations

import re

INTENTS = ("fact_query", "related_party", "relation_explain", "open_qa")

_FACT_KW = re.compile(r"前十大股东|十大股东|股东|高管|董监高|董事|监事|总经理|实控人|实际控制人|基本信息|注册|行业|市值")
_RELATION_KW = re.compile(r"关联方|关联关系|关联交易")
_TWO_ENTITY = re.compile(r"(\d{6})\s*(?:和|与|跟|及)\s*(\d{6})")
_RELATIONSHIP = re.compile(r"什么关系|关系|关联")


def extract_codes(question: str) -> list[str]:
    # 6 位数字且前后非数字(避开 8 位日期如 20251231); 不用 \b 因中文是 \w 无词边界
    return re.findall(r"(?<!\d)\d{6}(?!\d)", question)


def classify(question: str) -> str:
    q = question.strip()
    # 双实体 + 关系问句 -> relation_explain
    if _TWO_ENTITY.search(q) and _RELATIONSHIP.search(q):
        return "relation_explain"
    if _RELATION_KW.search(q):
        return "related_party"
    if _FACT_KW.search(q):
        return "fact_query"
    return "open_qa"
