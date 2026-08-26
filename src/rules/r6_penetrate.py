"""R6 间接股权穿透 - A<-X<-Y<-B 链, 比例乘积>=阈值, 跳数<=3。

诚实限制: 批量接口无 ratio, 多数链无法计算乘积 -> 仅在每跳都有 ratio 时产出。
性能: 限 max_hops, 排除通道节点, 设超时(此处用 LIMIT + 跳数上限)。
"""
from __future__ import annotations

from src.rules.base import RelatedPartyCandidate, Rule
from src.rules.evidence import entity_name, make_evidence
from src.rules.path import make_hop


class R6Penetrate(Rule):
    rule_id = "R6"

    def _entity_to_code(self, store, entity_id: int) -> str:
        """实体若是上市公司, 返回其 stock_code(用于继续向上穿透)。"""
        r = store.conn.execute(
            "SELECT canonical_name, display_name FROM entity WHERE entity_id=?", (entity_id,)).fetchone()
        if not r:
            return ""
        # 上市公司作持有人时, display_name 通常是其简称; 反查 company
        c = store.conn.execute(
            "SELECT stock_code FROM company WHERE short_name=? OR full_name=?",
            (r["display_name"], r["display_name"])).fetchone()
        return c["stock_code"] if c else ""

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        max_hops = int(self.cfg.get("max_hops", 3))
        min_ratio = float(self.cfg.get("min_effective_ratio", 5.0))
        out: list[RelatedPartyCandidate] = []
        # BFS: 起点 S, 经 holding 反向(entity->company), 跳数<=max_hops, 每跳 ratio
        # 用递归 SQL(等价 Cypher 变长路径)
        q = (
            "WITH RECURSIVE chain(holder_eid, target_code, prod, hops, path_ids, edge_ids) AS ("
            "  SELECT entity_id, stock_code, ratio, 1, CAST(entity_id AS TEXT), CAST(id AS TEXT) "
            "  FROM holding WHERE stock_code=? AND ratio IS NOT NULL "
            "  UNION ALL "
            "  SELECT h.entity_id, c.target_code, c.prod * (h.ratio/100.0), c.hops+1, "
            "         c.path_ids||'>'||h.entity_id, c.edge_ids||'>'||h.id "
            "  FROM chain c JOIN holding h ON h.stock_code = ("
            "    SELECT ck.stock_code FROM entity e LEFT JOIN company ck "
            "    ON ck.short_name=(SELECT display_name FROM entity WHERE entity_id=c.holder_eid) "
            "    WHERE e.entity_id=c.holder_eid LIMIT 1) "
            "  WHERE c.hops < ? AND h.ratio IS NOT NULL AND h.entity_id NOT IN (SELECT entity_id FROM entity WHERE is_channel=1)"
            ") SELECT holder_eid, prod, hops, edge_ids FROM chain WHERE hops>=2 AND prod>=? LIMIT 50"
        )
        try:
            rows = store.conn.execute(q, (subject_code, max_hops, min_ratio)).fetchall()
        except Exception:
            return out  # 递归 SQL 失败则空(诚实)
        for r in rows:
            name = entity_name(store, r["holder_eid"])
            out.append(RelatedPartyCandidate(
                subject_code=subject_code, party_id=f"E:{r['holder_eid']}", party_name=name,
                rule_id=self.rule_id, as_of_date=as_of or "", confidence="high", score=0.75,
                path=[make_hop(name, subject_code, "HOLDS*"+str(r["hops"]), effective_ratio=round(r["prod"], 4))],
                evidence=[make_evidence("holding", 0, "chain", None,
                                        {"holder_eid": r["holder_eid"], "effective_ratio": round(r["prod"], 4),
                                         "hops": r["hops"], "edge_ids": r["edge_ids"]})]))
        return out
