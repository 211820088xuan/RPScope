"""P5 指标 - P/R/F1 + 按规则 + 按置信度分档 + 三分类统计。

⚠️ gold_only/system_only 的语义见 aligner: system_only 不简单=FP(可能是真漏报=系统价值)。
"""
from __future__ import annotations

from collections import Counter


def prf(matched_n: int, system_only_n: int, gold_only_n: int) -> dict:
    tp = matched_n
    fp = system_only_n  # 严格口径(待人工核查修正)
    fn = gold_only_n
    p = tp / (tp + fp) if (tp + fp) else 0
    r = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * p * r / (p + r) if (p + r) else 0
    return {"precision": p, "recall": r, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def by_rule(per_company: list[dict]) -> dict[str, dict]:
    """每规则命中数(在 matched 集里的占比)。"""
    rule_matched = Counter(); rule_total = Counter()
    for r in per_company:
        for c in r["cands"]:
            for rid in set(c.rule_id.split("+")):
                rule_total[rid] += 1
                if norm_in(c.party_name, r["matched"]):
                    rule_matched[rid] += 1
    return {rid: {"matched": rule_matched[rid], "total": rule_total[rid],
                  "precision": rule_matched[rid] / rule_total[rid] if rule_total[rid] else 0}
            for rid in rule_total}


def norm_in(name, nameset) -> bool:
    from src.eval.aligner import norm_name
    return norm_name(name) in nameset


def by_confidence(per_company: list[dict]) -> dict[str, dict]:
    cm = Counter(); ct = Counter()
    for r in per_company:
        for c in r["cands"]:
            ct[c.confidence] += 1
            if norm_in(c.party_name, r["matched"]):
                cm[c.confidence] += 1
    return {conf: {"matched": cm[conf], "total": ct[conf],
                   "precision": cm[conf] / ct[conf] if ct[conf] else 0}
            for conf in ct}
