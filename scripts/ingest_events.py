"""P6 结构化事件入库 - 担保/诉讼(聚合) + 质押(明细, 出质人/质权人)。

从 P0 缓存读, 落 event 表。质押是成对的(出质人->质权人), 担保/诉讼仅聚合(无对手)。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.akshare_client import AkshareClient
from src.gold.mapper import map_party_to_entity
from src.normalize.name import normalize_name
from src.store.db import Store


def _f(v) -> float | None:
    try:
        import math
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def ingest_guarantee(store: Store, client: AkshareClient) -> int:
    df = client.get("stock_cg_guarantee_cninfo")  # 聚合: 担保笔数/金额 per 公司
    colmap = {normalize_name(c): c for c in df.columns}
    code_c = colmap.get(normalize_name("证券代码"))
    n_c = colmap.get(normalize_name("担保笔数"))
    amt_c = colmap.get(normalize_name("担保金额"))
    rng_c = colmap.get(normalize_name("公告统计区间"))
    n = 0
    for _, r in df.iterrows():
        code = str(r[code_c]).zfill(6) if code_c else ""
        if not code or code == "nan":
            continue
        store.upsert_event(event_type="guarantee", subject_code=code,
                           amount=_f(r[amt_c]) if amt_c else None,
                           summary=f"{r[n_c]}笔" if n_c else None,
                           event_date=str(r[rng_c]) if rng_c else None,
                           source_type="structured")
        n += 1
    return n


def ingest_lawsuit(store: Store, client: AkshareClient) -> int:
    df = client.get("stock_cg_lawsuit_cninfo")
    colmap = {normalize_name(c): c for c in df.columns}
    code_c = colmap.get(normalize_name("证券代码"))
    n_c = colmap.get(normalize_name("诉讼次数"))
    amt_c = colmap.get(normalize_name("诉讼金额"))
    rng_c = colmap.get(normalize_name("公告统计区间"))
    n = 0
    for _, r in df.iterrows():
        code = str(r[code_c]).zfill(6) if code_c else ""
        if not code or code == "nan":
            continue
        store.upsert_event(event_type="lawsuit", subject_code=code,
                           amount=_f(r[amt_c]) if amt_c else None,
                           summary=f"{r[n_c]}次" if n_c else None,
                           event_date=str(r[rng_c]) if rng_c else None,
                           source_type="structured")
        n += 1
    return n


def ingest_pledge(store: Store, client: AkshareClient) -> int:
    df = client.get("stock_cg_equity_mortgage_cninfo")  # 明细: 出质人/质权人
    colmap = {normalize_name(c): c for c in df.columns}
    code_c = colmap.get(normalize_name("股票代码"))
    date_c = colmap.get(normalize_name("公告日期"))
    pledgor_c = colmap.get(normalize_name("出质人"))
    pledgee_c = colmap.get(normalize_name("质权人"))
    amt_c = colmap.get(normalize_name("质押数量"))
    matter_c = colmap.get(normalize_name("质押事项"))
    n = 0
    for _, r in df.iterrows():
        code = str(r[code_c]).zfill(6) if code_c else ""
        if not code or code == "nan":
            continue
        pledgor = str(r[pledgor_c]) if pledgor_c else ""
        pledgee = str(r[pledgee_c]) if pledgee_c else ""
        cp = f"{pledgor} -> {pledgee}" if (pledgor or pledgee) else None
        eid = map_party_to_entity(store, pledgor) if pledgor else None
        store.upsert_event(event_type="pledge", subject_code=code, counterparty=cp,
                           counterparty_entity_id=eid, amount=_f(r[amt_c]) if amt_c else None,
                           summary=str(r[matter_c]) if matter_c else None,
                           event_date=str(r[date_c]) if date_c else None,
                           source_type="structured")
        n += 1
    return n


def main() -> None:
    store = Store("rpscope.db")
    client = AkshareClient()
    print("ingest 担保(聚合) ...", flush=True); ng = ingest_guarantee(store, client); store.commit(); print(f"  {ng}")
    print("ingest 诉讼(聚合) ...", flush=True); nl = ingest_lawsuit(store, client); store.commit(); print(f"  {nl}")
    print("ingest 质押(明细) ...", flush=True); np = ingest_pledge(store, client); store.commit(); print(f"  {np}")
    # 统计
    print("\n=== event 表统计 ===")
    for r in store.conn.execute(
            "SELECT event_type, source_type, COUNT(*) n FROM event GROUP BY event_type, source_type ORDER BY n DESC").fetchall():
        print(f"  {r[0]:10} {r[1]:12} {r[2]}")
    tot = store.conn.execute("SELECT COUNT(*) FROM event").fetchone()[0]
    n_co = store.conn.execute("SELECT COUNT(DISTINCT subject_code) FROM event").fetchone()[0]
    print(f"\n总事件 {tot} | 涉及公司 {n_co}")
    store.close()


if __name__ == "__main__":
    main()
