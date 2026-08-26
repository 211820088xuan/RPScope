"""R1 直接持股 - A 的股东 X 持股达阈值 -> X 是 A 的关联方。

阈值: control 50% / significant 20% / related_party 5%。
批量接口无 ratio -> holder_rank<=10 视为"前十大未披露比例" medium 置信。
"""
from __future__ import annotations

from src.rules.base import RelatedPartyCandidate, Rule
from src.rules.evidence import entity_name, make_evidence
from src.rules.path import make_hop


class R1Direct(Rule):
    rule_id = "R1"

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        th = self.cfg.get("thresholds", {})
        out: list[RelatedPartyCandidate] = []
        # GROUP BY entity_id: 同一股东多条 ggcg 变动记录只取 max(ratio), 不重复生成候选
        rows = store.conn.execute(
            "SELECT MAX(h.ratio) AS ratio, MAX(h.id) AS id, h.entity_id, "
            "MAX(h.holder_rank) AS holder_rank, MAX(h.report_period) AS report_period, "
            "MAX(h.source) AS source, e.is_channel, e.entity_type, e.confidence "
            "FROM holding h JOIN entity e ON h.entity_id=e.entity_id "
            "WHERE h.stock_code=? AND e.is_channel=0 "
            "GROUP BY h.entity_id, e.is_channel, e.entity_type, e.confidence", (subject_code,)).fetchall()
        for r in rows:
            if not self.valid_in(r, as_of):
                continue
            ratio = r["ratio"]
            if ratio is not None and ratio >= th.get("control", 50):
                conf, score = "high", 0.95
            elif ratio is not None and ratio >= th.get("significant", 20):
                conf, score = "high", 0.85
            elif ratio is not None and ratio >= th.get("related_party", 5):
                conf, score = "high", 0.75
            elif ratio is None and (r["holder_rank"] or 99) <= 10:
                conf, score = "medium", 0.5  # 前十大但比例未披露
            else:
                continue
            name = entity_name(store, r["entity_id"])
            out.append(RelatedPartyCandidate(
                subject_code=subject_code, party_id=f"E:{r['entity_id']}", party_name=name,
                rule_id=self.rule_id, as_of_date=as_of or "",
                path=[make_hop(name, subject_code, "HOLDS", ratio=ratio, rank=r["holder_rank"],
                               period=r["report_period"], source=r["source"])],
                evidence=[make_evidence("holding", r["id"], r["source"], r["report_period"],
                                        {"entity_id": r["entity_id"], "ratio": ratio, "rank": r["holder_rank"]})],
                confidence=conf, score=score))
        return out
