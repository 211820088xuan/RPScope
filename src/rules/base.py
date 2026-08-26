"""P3 规则引擎基类 - RelatedPartyCandidate + Rule ABC + as_of 有效性过滤。

铁律2: 本模块不调用任何 LLM。判定 100% 确定性。
每条候选带 rule_id/path/evidence/confidence/score/as_of_date, 可人工复核。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class RelatedPartyCandidate:
    subject_code: str          # 被分析的公司
    party_id: str              # 关联方 (entity_id 或 stock_code)
    party_name: str
    rule_id: str               # R1..R7
    path: list[dict] = field(default_factory=list)      # 每跳 {frm, to, edge, attrs}
    evidence: list[dict] = field(default_factory=list)  # {table, pk, source, report_period, raw}
    confidence: str = "medium"  # high | medium | low
    score: float = 0.0
    as_of_date: str = ""

    def key(self) -> tuple[str, str, str]:
        return (self.subject_code, self.party_id, self.rule_id)


class Rule:
    rule_id: str = ""

    def __init__(self, rule_cfg: dict[str, Any]) -> None:
        self.cfg = rule_cfg or {}
        self.enabled: bool = self.cfg.get("enabled", True)

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        raise NotImplementedError

    # ---- 工具: as_of 有效性过滤 ----
    @staticmethod
    def valid_in(row, as_of: str | None) -> bool:
        """边在 as_of 时点是否有效: valid_from<=as_of 且 (valid_to NULL 或 >=as_of)。"""
        vf = (row["valid_from"] or "") if "valid_from" in row.keys() else ""
        vt = (row["valid_to"] or "") if "valid_to" in row.keys() else ""
        if as_of:
            if vf and vf > as_of:
                return False
            if vt and vt < as_of:
                return False
        return True


def _merge_rules(a: str, b: str) -> str:
    """合并两个 rule_id(可能含 +)，去重排序。"""
    return "+".join(sorted(set(a.split("+") + b.split("+"))))


def merge_confidence(cands: list[RelatedPartyCandidate]) -> list[RelatedPartyCandidate]:
    """5.3 置信度合并: 同一 (subject, party) 多规则命中取最高置信, score 加 0.1*(命中规则数-1) 上限1.0。"""
    bucket: dict[tuple, RelatedPartyCandidate] = {}
    rank = {"high": 3, "medium": 2, "low": 1}
    for c in cands:
        k = (c.subject_code, c.party_id)
        if k not in bucket:
            bucket[k] = c
        else:
            cur = bucket[k]
            if rank.get(c.confidence, 0) > rank.get(cur.confidence, 0):
                c2 = RelatedPartyCandidate(
                    subject_code=c.subject_code, party_id=c.party_id, party_name=c.party_name,
                    rule_id=_merge_rules(cur.rule_id, c.rule_id),
                    path=cur.path[:1] + c.path[:1], evidence=cur.evidence + c.evidence,
                    confidence=c.confidence,
                    score=min(1.0, max(cur.score, c.score) + 0.1), as_of_date=c.as_of_date,
                )
                bucket[k] = c2
            else:
                cur.rule_id = _merge_rules(cur.rule_id, c.rule_id)
                cur.path = cur.path[:1] + c.path[:1]
                cur.evidence = cur.evidence + c.evidence
                cur.score = min(1.0, cur.score + 0.1)
    return list(bucket.values())
