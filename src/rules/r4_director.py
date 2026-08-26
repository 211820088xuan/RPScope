"""R4 连锁董事(交叉任职) - 同一自然人在 A,B 均任董监高 -> A,B 关联。⭐核心

置信度硬约束: 不得高于该人的消歧置信度(实体表 confidence 字段)。
title_classes 不含 independent_director(独董兼职普遍, 会污染)。
依赖 P2 消歧: 同名不同人已拆分 -> 同 entity_id 即同人。
"""
from __future__ import annotations

from src.rules.base import RelatedPartyCandidate, Rule
from src.rules.evidence import entity_name, make_evidence
from src.rules.path import make_hop

_CONF_RANK = {"high": 3, "medium": 2, "low": 1}


class R4ChainDirector(Rule):
    rule_id = "R4"

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        tcs = self.cfg.get("title_classes", ["director", "supervisor", "senior_mgmt"])
        ph = ",".join("?" for _ in tcs)
        out: list[RelatedPartyCandidate] = []
        # S 的董监高
        directors = store.conn.execute(
            f"SELECT id, entity_id, title, title_class, valid_from, source FROM position "
            f"WHERE stock_code=? AND title_class IN ({ph})", (subject_code, *tcs)).fetchall()
        for d in directors:
            if not self.valid_in(d, as_of):
                continue
            # 该人在其他公司的任职
            others = store.conn.execute(
                "SELECT id, stock_code, title, title_class, valid_from, source FROM position "
                "WHERE entity_id=? AND stock_code<>?", (d["entity_id"], subject_code)).fetchall()
            if not others:
                continue
            # 消歧置信度: R4 不得高于它
            ent = store.conn.execute(
                "SELECT display_name, confidence, is_channel FROM entity WHERE entity_id=?",
                (d["entity_id"],)).fetchone()
            if not ent or ent["is_channel"]:
                continue
            disambig_conf = _CONF_RANK.get(ent["confidence"] or "medium", 2)
            r4_conf = "high" if disambig_conf >= 3 else (ent["confidence"] or "medium")
            for o in others:
                if not self.valid_in(o, as_of):
                    continue
                oname = store.conn.execute(
                    "SELECT short_name FROM company WHERE stock_code=?", (o["stock_code"],)).fetchone()
                oname = oname["short_name"] if oname else o["stock_code"]
                out.append(RelatedPartyCandidate(
                    subject_code=subject_code, party_id=f"C:{o['stock_code']}", party_name=oname,
                    rule_id=self.rule_id, as_of_date=as_of or "", confidence=r4_conf, score=0.7,
                    path=[make_hop(subject_code, ent["display_name"] or "", "SERVED_BY", title=d["title"], title_class=d["title_class"]),
                          make_hop(ent["display_name"] or "", o["stock_code"], "SERVES_AS", title=o["title"], title_class=o["title_class"])],
                    evidence=[make_evidence("position", d["id"], d["source"], None, {"entity_id": d["entity_id"], "title": d["title"]}),
                              make_evidence("position", o["id"], o["source"], None, {"brother": o["stock_code"], "title": o["title"]})]))
        return out
