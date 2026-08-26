"""P2 消歧解析器 - 加权融合 + 3 档阈值 + LLM 兜底中段。

档位:
  score > 0.75  -> same_person, confidence=high
  score < 0.35  -> different_person, confidence=high
  中间区间       -> 调 LLM 兜底, confidence=medium; LLM 不确定 -> different, low (保守)
每个判定写 disambig_note, 可复核。
R4 的置信度不得高于其消歧置信度(硬约束, 在 P3 规则引擎里读这个字段)。
"""
from __future__ import annotations

from dataclasses import dataclass

from src.disambiguate.llm_fallback import llm_judge
from src.disambiguate.signals import Record, Stats, score_pair
from src.llm.client import LLMClient

HIGH_SAME = 0.70
LOW_DIFF = 0.40


@dataclass
class Verdict:
    same_person: bool
    confidence: str          # high | medium | low
    score: float
    note: str
    used_llm: bool


def resolve_pair(name: str, rec_a: Record, rec_b: Record, stats: Stats,
                 client: LLMClient | None = None) -> Verdict:
    score, parts, why = score_pair(name, rec_a, rec_b, stats)
    if score > HIGH_SAME:
        return Verdict(True, "high", score, f"规则同人 {score}: {'; '.join(why)}", False)
    if score < LOW_DIFF:
        return Verdict(False, "high", score, f"规则不同人 {score}: {'; '.join(why)}", False)
    # 中段 -> LLM 兜底
    if client is None or not client.enabled:
        # 无 LLM: 保守判不同人, medium
        return Verdict(False, "medium", score, f"无LLM保守判不同人 {score}: {'; '.join(why)}", False)
    same, conf, reason = llm_judge(name, rec_a, rec_b, client)
    confidence = "medium" if conf >= 0.6 else "low"
    return Verdict(same, confidence, score,
                   f"LLM兜底({same},{conf:.2f}) 规则分{score}: {reason}", True)
