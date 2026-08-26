"""R5 关键人关联 - A 的董监高 P 同时是 B 的重要股东(>=5%)(或反之)。

持股记录是强同一人证据 -> high 置信。
"""
from __future__ import annotations

from src.rules.base import RelatedPartyCandidate, Rule
from src.rules.evidence import entity_name, make_evidence
from src.rules.path import make_hop


class R5KeyPerson(Rule):
    rule_id = "R5"

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        th = self.cfg.get("thresholds", {}).get("min_ratio", 5.0)
        tcs = self.cfg.get("title_classes", ["director", "supervisor", "senior_mgmt"])
        ph = ",".join("?" for _ in tcs)
        out: list[RelatedPartyCandidate] = []
        # S 的董监高 P
        directors = store.conn.execute(
            f"SELECT id, entity_id, title, valid_from, source FROM position "
            f"WHERE stock_code=? AND title_class IN ({ph})", (subject_code, *tcs)).fetchall()
        for d in directors:
            if not self.valid_in(d, as_of):
                continue
            # P 在其他公司的持股 >= 阈值
            holds = store.conn.execute(
                "SELECT id, stock_code, ratio, report_period, source FROM holding "
                "WHERE entity_id=? AND stock_code<>? AND ratio>=?",
                (d["entity_id"], subject_code, th)).fetchall()
            for h in holds:
                if not self.valid_in(h, as_of):
                    continue
                pname = entity_name(store, d["entity_id"])
                oname = store.conn.execute(
                    "SELECT short_name FROM company WHERE stock_code=?", (h["stock_code"],)).fetchone()
                oname = oname["short_name"] if oname else h["stock_code"]
                out.append(RelatedPartyCandidate(
                    subject_code=subject_code, party_id=f"C:{h['stock_code']}", party_name=oname,
                    rule_id=self.rule_id, as_of_date=as_of or "", confidence="high", score=0.8,
                    path=[make_hop(subject_code, pname, "SERVED_BY", title=d["title"]),
                          make_hop(pname, h["stock_code"], "HOLDS", ratio=h["ratio"], period=h["report_period"])],
                    evidence=[make_evidence("position", d["id"], d["source"], None, {"entity_id": d["entity_id"]}),
                              make_evidence("holding", h["id"], h["source"], h["report_period"], {"brother": h["stock_code"], "ratio": h["ratio"]})]))
        return out
