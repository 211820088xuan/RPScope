"""T2: 意图分类器 — 规则优先, LLM 兜底。

7 类意图:
  Q1 related_party     查某公司的关联方
  Q2 relation_path     查两个实体间的关系路径
  Q3 reverse_control   反向查询某人/机构控制或持股哪些公司
  Q4 company_role      查某公司的股东/董监高/实控人
  Q5 risk_events       查某公司的风险事件
  Q6 overlap           两家公司的关联方重合
  Q7 open              模板外(兜底)
"""
from __future__ import annotations
import re, yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "intent_keywords.yaml"
_CFG: dict | None = None


def _load_config() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return _CFG


def _check_patterns(question: str, patterns: list[str]) -> bool:
    for p in patterns:
        if re.match(p, question):
            return True
    return False


def _check_keywords(question: str, keywords: list[str]) -> bool:
    return any(kw in question for kw in keywords)


# 两实体检测(两个6位代码, 或 "A和B" 句式)
_TWO_CODE = re.compile(r"(\d{6})\s*(?:和|与|跟|及)\s*(\d{6})")
_TWO_ENTITY_PATTERN = re.compile(r"([\u4e00-\u9fa5A-Za-z]{2,15})\s*(?:和|与|跟|及)\s*([\u4e00-\u9fa5A-Za-z]{2,15}).*(?:关系|关联|重合|交集|重叠)")


def classify(question: str) -> dict:
    """规则分类, 返回 {intent, confidence, rule_hit, uncertain}。"""
    q = question.strip()
    cfg = _load_config()

    # Q8: 对比分析 (优先于 Q6)
    if _check_keywords(q, ["对比", "比较", "比较一下", "对比一下", "区别", "差异"]):
        return {"intent": "Q8", "confidence": 0.95, "rule_hit": "compare_keyword", "uncertain": False}

    # Q6: 两公司 + 关联方重合/交集
    if _check_keywords(q, cfg["Q6_overlap"]["keywords"]) or _check_patterns(q, cfg["Q6_overlap"]["patterns"]):
        return {"intent": "Q6", "confidence": 0.95, "rule_hit": "keyword/pattern", "uncertain": False}

    # Q2: 两实体 + 关系问句
    if _TWO_CODE.search(q) and _check_keywords(q, cfg["Q2_relation_path"]["keywords"]):
        return {"intent": "Q2", "confidence": 0.95, "rule_hit": "two_code+keyword", "uncertain": False}
    if _TWO_ENTITY_PATTERN.search(q) and _check_keywords(q, cfg["Q2_relation_path"]["keywords"]):
        return {"intent": "Q2", "confidence": 0.85, "rule_hit": "two_entity+keyword", "uncertain": False}

    # Q3: 反向查询(某人/机构控制/持股/任职哪些公司)
    if _check_patterns(q, cfg["Q3_reverse_control"]["patterns"]):
        return {"intent": "Q3", "confidence": 0.9, "rule_hit": "pattern", "uncertain": False}
    if _check_keywords(q, cfg["Q3_reverse_control"]["keywords"]) and ("哪些" in q or "哪家" in q or "哪些公司" in q):
        return {"intent": "Q3", "confidence": 0.85, "rule_hit": "keyword+哪些", "uncertain": False}

    # Q5: 风险事件
    if _check_keywords(q, cfg["Q5_risk_events"]["keywords"]) or _check_patterns(q, cfg["Q5_risk_events"]["patterns"]):
        return {"intent": "Q5", "confidence": 0.9, "rule_hit": "keyword/pattern", "uncertain": False}

    # Q4: 公司角色(股东/董监高/实控人) — 要在 Q1 之前判, 因为"关联方"不含"股东"
    if _check_keywords(q, cfg["Q4_company_role"]["keywords"]) or _check_patterns(q, cfg["Q4_company_role"]["patterns"]):
        return {"intent": "Q4", "confidence": 0.9, "rule_hit": "keyword/pattern", "uncertain": False}

    # Q1: 关联方
    if _check_keywords(q, cfg["Q1_related_party"]["keywords"]) or _check_patterns(q, cfg["Q1_related_party"]["patterns"]):
        return {"intent": "Q1", "confidence": 0.9, "rule_hit": "keyword/pattern", "uncertain": False}

    # Q7: 模板外
    return {"intent": "Q7", "confidence": 0.3, "rule_hit": "fallback", "uncertain": True}
