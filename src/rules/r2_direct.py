"""R2 同一控制(共同实控人) - A 与 B 有同一实际控制人 -> A,B 互为关联方。⭐核心

准则: 同受国家控制不构成关联方 -> 控制人实体 is_channel=1(政府/国资委)时跳过。
实控人是官方披露强信号 -> high 置信。
"""
from __future__ import annotations

from src.rules.base import RelatedPartyCandidate, Rule
from src.rules.evidence import entity_name, make_evidence
from src.rules.path import make_hop


class R2SameControl(Rule):
    rule_id = "R2"

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        out: list[RelatedPartyCandidate] = []
        # S 的控制人(过滤 is_channel=1 的政府控制人)
        ctrls = store.conn.execute(
            "SELECT ac.id, ac.entity_id, ac.control_ratio, ac.valid_from, ac.source "
            "FROM actual_controller ac JOIN entity e ON ac.entity_id=e.entity_id "
            "WHERE ac.stock_code=? AND e.is_channel=0", (subject_code,)).fetchall()
        for c in ctrls:
            if not self.valid_in(c, as_of):
                continue
            ctrl_name = entity_name(store, c["entity_id"])
            # 同一控制人下的其他公司(兄弟公司)
            brothers = store.conn.execute(
                "SELECT id, stock_code, valid_from, source FROM actual_controller "
                "WHERE entity_id=? AND stock_code<>?", (c["entity_id"], subject_code)).fetchall()
            for b in brothers:
                if not self.valid_in(b, as_of):
                    continue
                bname = store.conn.execute(
                    "SELECT short_name FROM company WHERE stock_code=?", (b["stock_code"],)).fetchone()
                bname = bname["short_name"] if bname else b["stock_code"]
                out.append(RelatedPartyCandidate(
                    subject_code=subject_code, party_id=f"C:{b['stock_code']}", party_name=bname,
                    rule_id=self.rule_id, as_of_date=as_of or "", confidence="high", score=0.9,
                    path=[make_hop(subject_code, ctrl_name, "CONTROLLED_BY", ratio=c["control_ratio"]),
                          make_hop(ctrl_name, b["stock_code"], "CONTROLS", source=b["source"])],
                    evidence=[make_evidence("actual_controller", c["id"], c["source"], None,
                                            {"controller": ctrl_name, "entity_id": c["entity_id"]}),
                              make_evidence("actual_controller", b["id"], b["source"], None,
                                            {"brother": b["stock_code"]})]))
        return out
