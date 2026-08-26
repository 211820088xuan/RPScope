"""R7 事件型关联 - 担保/共同投资/重大交易对手等事件揭示的关联。

诚实限制: 当前 ingested 的 stock_cg_guarantee_cninfo 仅聚合(担保笔数/金额 per 公司),
非成对(A 担保 B)边。成对担保关系需 P6 从公告文本抽取(结构化接口不提供对手方)。
故 R7 当前仅作"风险上下文"(subject 自身的担保聚合), 不进关联方主结论集。
P6 文本抽取接入后, 此规则返回真正成对边。
"""
from __future__ import annotations

from src.rules.base import RelatedPartyCandidate, Rule


class R7Event(Rule):
    rule_id = "R7"

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        # 检查是否有成对担保表(P6 之后会有 guarantee_pair); 当前无 -> 空列表
        try:
            tbl = store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='guarantee_pair'").fetchone()
        except Exception:
            tbl = None
        if not tbl:
            return []  # 无成对担保数据, 诚实返回空
        rows = store.conn.execute(
            "SELECT id, counterparty_code, amount, source, event_date FROM guarantee_pair "
            "WHERE subject_code=? OR counterparty_code=?", (subject_code, subject_code)).fetchall()
        out: list[RelatedPartyCandidate] = []
        for r in rows:
            cp = r["counterparty_code"] if r["counterparty_code"] != subject_code else r["subject_code"] if "subject_code" in r.keys() else ""
            if not cp:
                continue
            out.append(RelatedPartyCandidate(
                subject_code=subject_code, party_id=f"C:{cp}", party_name=cp,
                rule_id=self.rule_id, as_of_date=as_of or "", confidence="high", score=0.7,
                evidence=[{"table": "guarantee_pair", "pk": r["id"], "source": r["source"],
                           "report_period": r["event_date"], "raw": {"amount": r["amount"]}}]))
        return out
