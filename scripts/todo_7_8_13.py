"""#7 全量消歧拆分(rule-only) + #8 并发压测 + #13 gold抽检30家。"""
import sys, os, time, threading, sqlite3, csv, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ============================================================
# #7: 全量 person 消歧拆分 (rule-only, 无 LLM)
# ============================================================
def t7_full_disambig():
    os.environ["RPSCOPE_LLM_ENABLED"] = "false"
    # 清理旧 #D 实体(已被 #6 撤销, 0 记录)
    store_conn = sqlite3.connect("rpscope.db")
    n_del = store_conn.execute("DELETE FROM entity WHERE canonical_name LIKE '%#D%'").rowcount
    store_conn.commit(); store_conn.close()
    print(f"#7: 清理旧 #D 实体 {n_del} 个")

    # 重新 import (env var 已设)
    import importlib
    from src.data.ingest import EntityCache, _strip_code_prefix
    from src.store.db import Store
    from dataclasses import dataclass as _dc

    @_dc
    class Rec:
        table: str
        rowid: int
        stock_code: str
        title: str
        valid_from: str
        source: str

    def pull_records(store, entity_id, limit=150):
        rows = list(store.conn.execute(
            "SELECT 'position' t, id, stock_code, title, valid_from, source FROM position WHERE entity_id=? "
            "UNION ALL SELECT 'holding', id, stock_code, '', valid_from, source FROM holding WHERE entity_id=? "
            "LIMIT ?", (entity_id, entity_id, limit)))
        return [Rec(r[0], r[1], r[2] or "", r[3] or "", r[4] or "", r[5] or "") for r in rows]

    store = Store("rpscope.db")
    from src.disambiguate.resolver import resolve_pair
    from src.disambiguate.cluster import greedy_cluster
    from src.disambiguate.signals import Record, Stats
    importlib.reload(sys.modules["src.llm.client"])
    from src.llm.client import LLMClient
    llm = LLMClient()
    print(f"  LLM enabled={llm.enabled} (应为 False, rule-only)")

    store = Store("rpscope.db")
    merged = list(store.conn.execute(
        "SELECT * FROM ("
        "  SELECT e.entity_id, e.canonical_name, e.display_name, "
        "    (SELECT COUNT(*) FROM position p WHERE p.entity_id=e.entity_id) + "
        "    (SELECT COUNT(*) FROM holding h WHERE h.entity_id=e.entity_id) AS n "
        "  FROM entity e WHERE e.entity_type='person' AND e.is_channel=0 AND e.canonical_name NOT LIKE '%#D%'"
        ") WHERE n > 20 ORDER BY n DESC LIMIT 100"))
    print(f"  高合并 person 实体: {len(merged)} 个")

    total_split = 0
    for idx, r in enumerate(merged):
        eid, canon, disp, n_before = r["entity_id"], r["canonical_name"], r["display_name"], r["n"]
        recs = pull_records(store, eid, 150)
        if len(recs) < 5:
            continue
        n_co = store.conn.execute(
            "SELECT COUNT(DISTINCT stock_code) FROM ("
            "  SELECT stock_code FROM position WHERE entity_id=? UNION SELECT stock_code FROM holding WHERE entity_id=?)",
            (eid, eid)).fetchone()[0]
        stats = Stats(name_freq=len(recs), name_company_count=n_co)

        def decider(i, rep_i):
            ra, rb = recs[rep_i], recs[i]
            ra_r = Record(stock_code=ra.stock_code, title=ra.title, valid_from=ra.valid_from, source=ra.source)
            rb_r = Record(stock_code=rb.stock_code, title=rb.title, valid_from=rb.valid_from, source=rb.source)
            v = resolve_pair(disp, ra_r, rb_r, stats, None)  # rule-only, 无 LLM
            return v

        clusters = greedy_cluster(len(recs), decider)
        if len(clusters) <= 1:
            continue
        # split
        import json as _json
        for ci in range(1, len(clusters)):
            new_canonical = f"{canon}#D{ci + 1}"
            note = f"split from E:{eid} cluster{ci + 1} (rule-only, records={len(clusters[ci])})"
            raw_names = _json.dumps([disp], ensure_ascii=False)
            cur = store.conn.execute(
                "INSERT INTO entity(entity_type, canonical_name, display_name, raw_names, is_channel, confidence, disambig_note) "
                "VALUES(?,?,?,?,0,'medium',?)",
                ('person', new_canonical, disp, raw_names, note))
            new_id = int(cur.lastrowid)
            for ri in clusters[ci]:
                r2 = recs[ri]
                store.conn.execute(f"UPDATE {r2.table} SET entity_id=? WHERE id=?", (new_id, r2.rowid))
            total_split += 1
        if (idx + 1) % 20 == 0:
            store.commit()
            print(f"  [{idx+1}/{len(merged)}] 拆出 {total_split} 新簇", flush=True)
    store.commit()
    print(f"  总拆出: {total_split} 个新 person 实体")

    # 重建图
    from src.graph.store import build_graph, save_graph
    G = build_graph(store)
    save_graph(G)
    distinct_deg = {n: len(set(G.successors(n)) | set(G.predecessors(n))) for n in G}
    top = sorted(distinct_deg.items(), key=lambda x: x[1], reverse=True)[:5]
    max_deg = top[0][1] if top else 0
    print(f"  重建图: {G.number_of_nodes()} 节点 {G.number_of_edges()} 边, max-degree={max_deg}")
    store.close()
    return max_deg


# ============================================================
# #8: 并发压测 (TestClient + threading)
# ============================================================
def t8_concurrency_test():
    from fastapi.testclient import TestClient
    from src.serve.main import app
    c = TestClient(app)
    results = []
    lock = threading.Lock()

    def hit(i):
        t0 = time.perf_counter()
        try:
            r = c.get(f"/api/report/002594")
            ok = r.status_code == 200
        except:
            ok = False
        dt = (time.perf_counter() - t0) * 1000
        with lock:
            results.append((dt, ok))

    threads = []
    for i in range(20):
        t = threading.Thread(target=hit, args=(i,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    times = sorted(dt for dt, ok in results)
    p50 = times[len(times)//2]
    p95 = times[int(len(times)*0.95)]
    ok_rate = sum(1 for _, ok in results if ok) / len(results)
    print(f"#8: 20 并发 GET /api/report/002594")
    print(f"  P50={p50:.0f}ms P95={p95:.0f}ms 成功率={ok_rate*100:.0f}%")
    print(f"  (TestClient 线程并发, 非真实 server; 但测了 SQLite check_same_thread=False + 并发读)")


# ============================================================
# #13: gold 抽检 30 家
# ============================================================
def t13_gold_audit():
    from src.store.db import Store
    store = Store("rpscope.db")
    import random; random.seed(42)
    codes = [r[0] for r in store.conn.execute("SELECT DISTINCT stock_code FROM gold_related_party").fetchall()]
    sample = random.sample(codes, min(30, len(codes)))
    out = Path("data/reviews/gold_audit_30.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock_code", "gold_count", "upstream_count", "downstream_count", "mapped_count", "audit_ok"])
        for code in sample:
            gc = store.conn.execute("SELECT COUNT(*) FROM gold_related_party WHERE stock_code=?", (code,)).fetchone()[0]
            uc = store.conn.execute("SELECT COUNT(*) FROM gold_related_party WHERE stock_code=? AND scope_class='upstream'", (code,)).fetchone()[0]
            dc = store.conn.execute("SELECT COUNT(*) FROM gold_related_party WHERE stock_code=? AND scope_class='downstream'", (code,)).fetchone()[0]
            mc = store.conn.execute("SELECT COUNT(*) FROM gold_related_party WHERE stock_code=? AND party_entity_id IS NOT NULL", (code,)).fetchone()[0]
            w.writerow([code, gc, uc, dc, mc, ""])
    print(f"#13: 30 家抽检表 -> {out}")
    # 统计
    print(f"  平均 gold/家: {sum(store.conn.execute('SELECT COUNT(*) FROM gold_related_party WHERE stock_code=?',(c,)).fetchone()[0] for c in sample)/len(sample):.1f}")
    store.close()


if __name__ == "__main__":
    print("=== #7: 全量消歧拆分 ===")
    t7_full_disambig()
    print("\n=== #8: 并发压测 ===")
    t8_concurrency_test()
    print("\n=== #13: gold抽检30家 ===")
    t13_gold_audit()
    print("\n完成 #7 + #8 + #13")
