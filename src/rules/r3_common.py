"""R3 共同重要股东 - A,B 被同一股东 X 持有且两边均达阈值 -> 关联。⭐但 P0 实测近失效

P0 发现: 排除通道后共同股东对密度 0.3% -> 降级 low 置信, 仅作上下文。
要求 report_period 一致(防跨期假共同)。ratio 缺失时跳过(无法判定)。
"""
from __future__ import annotations

from src.rules.base import RelatedPartyCandidate, Rule
from src.rules.evidence import entity_name, make_evidence
from src.rules.path import make_hop


class R3CommonHolder(Rule):
    rule_id = "R3"

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        th = self.cfg.get("thresholds", {}).get("min_ratio", 5.0)
        require_same = self.cfg.get("require_same_period", True)
        out: list[RelatedPartyCandidate] = []
        # S 的股东(非通道, 有 ratio)
        holders = store.conn.execute(
            "SELECT h.id, h.entity_id, h.ratio, h.report_period, h.source, h.holder_rank "
            "FROM holding h JOIN entity e ON h.entity_id=e.entity_id "
            "WHERE h.stock_code=? AND e.is_channel=0 AND h.ratio IS NOT NULL", (subject_code,)).fetchall()
        for hx in holders:
            if not self.valid_in(hx, as_of) or (hx["ratio"] or 0) < th:
                continue
            # 该股东持有的其他公司(同期, 同样>=阈值)
            q = ("SELECT id, stock_code, ratio, report_period, source FROM holding "
                 "WHERE entity_id=? AND stock_code<>? AND ratio>=?")
            params: list = [hx["entity_id"], subject_code, th]
            if require_same:
                q += " AND report_period=?"
                params.append(hx["report_period"])
            others = store.conn.execute(q, params).fetchall()
            for o in others:
                if not self.valid_in(o, as_of):
                    continue
                xname = entity_name(store, hx["entity_id"])
                oname = store.conn.execute(
                    "SELECT short_name FROM company WHERE stock_code=?", (o["stock_code"],)).fetchone()
                oname = oname["short_name"] if oname else o["stock_code"]
                out.append(RelatedPartyCandidate(
                    subject_code=subject_code, party_id=f"C:{o['stock_code']}", party_name=oname,
                    rule_id=self.rule_id, as_of_date=as_of or "", confidence="low", score=0.3,
                    path=[make_hop(subject_code, xname, "HELD_BY", ratio=hx["ratio"], period=hx["report_period"]),
                          make_hop(xname, o["stock_code"], "HOLDS", ratio=o["ratio"], period=o["report_period"])],
                    evidence=[make_evidence("holding", hx["id"], hx["source"], hx["report_period"], {"entity_id": hx["entity_id"]}),
                              make_evidence("holding", o["id"], o["source"], o["report_period"], {"brother": o["stock_code"]})]))
        return out
