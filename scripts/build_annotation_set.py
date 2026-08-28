"""P2 构建消歧标注集 - 抽 250 对同名候选, 分层(高/中/低分各1/3), 输出 jsonl 供人工标注。

每条含两侧完整上下文(公司/职务/日期/来源), 留 same_person 字段空给人工填。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.disambiguate.resolver import resolve_pair
from src.disambiguate.signals import Record, Stats
from src.llm.client import LLMClient
from src.store.db import Store

OUT = Path("data/annotations/person_disambig.jsonl")


def main(n_per_tier: int = 85) -> None:
    # 生成标注集: 扩到 200+ 对(分层 high/mid/low 各 ~70)
    # 原 85/层=255 但去重后 90; 改为取更多候选公司
    store = Store("rpscope.db")
    client = LLMClient()
    # 找记录数>=4 的 person 实体(才能抽同实体内不同记录的对)
    cands = list(store.conn.execute(
        "SELECT * FROM ("
        "  SELECT e.entity_id, e.canonical_name, e.display_name, "
        "    (SELECT COUNT(*) FROM position p WHERE p.entity_id=e.entity_id) + "
        "    (SELECT COUNT(*) FROM holding h WHERE h.entity_id=e.entity_id) AS n "
        "  FROM entity e WHERE e.entity_type='person' AND e.is_channel=0 AND e.canonical_name NOT LIKE '%#D%'"
        ") WHERE n BETWEEN 2 AND 30 ORDER BY n DESC LIMIT 500"))

    pairs: list[dict] = []
    for r in cands:
        eid, canon, disp = r[0], r[1], r[2]
        recs = list(store.conn.execute(
            "SELECT 'position' t, id, stock_code, title, valid_from, source FROM position WHERE entity_id=? "
            "UNION ALL SELECT 'holding', id, stock_code, '', valid_from, source FROM holding WHERE entity_id=? "
            "LIMIT 20", (eid, eid)))
        if len(recs) < 2:
            continue
        # 取首末两条作一对(避免组合爆炸)
        a, b = recs[0], recs[-1]
        ra = Record(a[2] or "", a[3] or "", a[4] or "", a[5] or "")
        rb = Record(b[2] or "", b[3] or "", b[4] or "", b[5] or "")
        n_co = store.conn.execute(
            "SELECT COUNT(DISTINCT stock_code) FROM ("
            "  SELECT stock_code FROM position WHERE entity_id=? UNION SELECT stock_code FROM holding WHERE entity_id=?)",
            (eid, eid)).fetchone()[0]
        stats = Stats(name_freq=len(recs), name_company_count=n_co)
        v = resolve_pair(disp, ra, rb, stats, client=None)  # 标注集只用规则分分层, 不调 LLM
        pairs.append({
            "name": disp, "canonical": canon,
            "rec_a": {"table": a[0], "stock_code": a[2], "title": a[3], "valid_from": a[4], "source": a[5]},
            "rec_b": {"table": b[0], "stock_code": b[2], "title": b[3], "valid_from": b[4], "source": b[5]},
            "rule_score": v.score, "tier": ("high" if v.score > 0.75 else "low" if v.score < 0.35 else "mid"),
            "same_person": "",  # 人工填: true/false
            "note": "",
        })

    # 分层各取 n_per_tier
    by_tier: dict[str, list] = {"high": [], "mid": [], "low": []}
    for p in pairs:
        by_tier[p["tier"]].append(p)
    out = []
    for t in ("high", "mid", "low"):
        out.extend(by_tier[t][:n_per_tier])
    # 不够则全取 mid
    if len(out) < 200:
        remaining = [p for p in by_tier["mid"] if p not in out]
        out.extend(remaining[:200 - len(out)])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for p in out:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"抽出 {len(out)} 对同名候选 -> {OUT}")
    print(f"  high(>0.75): {len(by_tier['high'])} | mid: {len(by_tier['mid'])} | low(<0.35): {len(by_tier['low'])} (取前{n_per_tier}/层)")
    print("人工标注: 填 same_person=true/false, 然后跑 scripts/eval_disambig.py")


if __name__ == "__main__":
    main()
