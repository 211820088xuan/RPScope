"""清理所有 #D 实体(reassign 记录回 parent, 删 #D) + 用 LLM 重跑消歧。"""
import sys, sqlite3, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

print("=== 1. 清理 #D 实体 ===")
c = sqlite3.connect("rpscope.db"); c.row_factory = sqlite3.Row
# 找所有 #D 实体 + parent
d_rows = list(c.execute("SELECT entity_id, canonical_name, display_name FROM entity WHERE canonical_name LIKE '%#D%'").fetchall())
print(f"  #D 实体: {len(d_rows)}")
# 每个 #D 的 parent = 同 display_name 但无 #D 的 entity
for d in d_rows:
    parent = c.execute("SELECT entity_id FROM entity WHERE display_name=? AND canonical_name NOT LIKE '%#D%' LIMIT 1", (d["display_name"],)).fetchone()
    if parent:
        pid = parent[0]
        c.execute("UPDATE position SET entity_id=? WHERE entity_id=?", (pid, d["entity_id"]))
        c.execute("UPDATE holding SET entity_id=? WHERE entity_id=?", (pid, d["entity_id"]))
c.execute("DELETE FROM entity WHERE canonical_name LIKE '%#D%'")
c.commit()
# 验证
n_d = c.execute("SELECT COUNT(*) FROM entity WHERE canonical_name LIKE '%#D%'").fetchone()[0]
print(f"  清理后 #D 残留: {n_d}")
c.close()

print("\n=== 2. LLM 消歧重跑(top-10) ===")
# 用 apply_disambig 的逻辑, 但 LIMIT=10
from src.store.db import Store
from src.llm.client import LLMClient
from src.disambiguate.cluster import greedy_cluster
from src.disambiguate.resolver import resolve_pair
from src.disambiguate.signals import Record, Stats
from src.graph.store import build_graph, save_graph
from dataclasses import dataclass
import json

@dataclass
class Rec:
    table: str; rowid: int; stock_code: str; title: str; valid_from: str; source: str

def pull_records(store, eid, limit=150):
    rows = list(store.conn.execute(
        "SELECT 'position' t, id, stock_code, title, valid_from, source FROM position WHERE entity_id=? "
        "UNION ALL SELECT 'holding', id, stock_code, '', valid_from, source FROM holding WHERE entity_id=? "
        "LIMIT ?", (eid, eid, limit)))
    return [Rec(r[0], r[1], r[2] or "", r[3] or "", r[4] or "", r[5] or "") for r in rows]

store = Store("rpscope.db")
llm = LLMClient()
print(f"  LLM enabled={llm.enabled}")

merged = list(store.conn.execute(
    "SELECT * FROM ("
    "  SELECT e.entity_id, e.canonical_name, e.display_name, "
    "    (SELECT COUNT(*) FROM position p WHERE p.entity_id=e.entity_id) + "
    "    (SELECT COUNT(*) FROM holding h WHERE h.entity_id=e.entity_id) AS n "
    "  FROM entity e WHERE e.entity_type='person' AND e.is_channel=0 AND e.canonical_name NOT LIKE '%#D%'"
    ") WHERE n > 20 ORDER BY n DESC LIMIT 10"))
print(f"  top-10 高合并 person: {len(merged)} 个")

total_split = 0
llm_budget = [8]  # 每人最多 8 次 LLM
for idx, r in enumerate(merged):
    eid, canon, disp = r["entity_id"], r["canonical_name"], r["display_name"]
    recs = pull_records(store, eid, 150)
    if len(recs) < 5: continue
    n_co = store.conn.execute(
        "SELECT COUNT(DISTINCT stock_code) FROM ("
        "  SELECT stock_code FROM position WHERE entity_id=? UNION SELECT stock_code FROM holding WHERE entity_id=?)",
        (eid, eid)).fetchone()[0]
    stats = Stats(name_freq=len(recs), name_company_count=n_co)
    
    def make_decider(recs_list):
        def decider(i, rep_i):
            ra, rb = recs_list[rep_i], recs_list[i]
            ra_r = Record(stock_code=ra.stock_code, title=ra.title, valid_from=ra.valid_from, source=ra.source)
            rb_r = Record(stock_code=rb.stock_code, title=rb.title, valid_from=rb.valid_from, source=rb.source)
            use_llm = llm if llm_budget[0] > 0 else None
            if use_llm is not None: llm_budget[0] -= 1
            v = resolve_pair(disp, ra_r, rb_r, stats, use_llm)
            return v
        return decider
    
    clusters = greedy_cluster(len(recs), make_decider(recs))
    llm_budget[0] = 8  # reset for next person
    if len(clusters) <= 1: continue
    for ci in range(1, len(clusters)):
        new_canonical = f"{canon}#D{ci + 1}"
        note = f"LLM split from E:{eid} cluster{ci + 1} (records={len(clusters[ci])})"
        raw_names = json.dumps([disp], ensure_ascii=False)
        cur = store.conn.execute(
            "INSERT INTO entity(entity_type, canonical_name, display_name, raw_names, is_channel, confidence, disambig_note) "
            "VALUES(?,?,?,?,0,'medium',?)",
            ('person', new_canonical, disp, raw_names, note))
        new_id = int(cur.lastrowid)
        for ri in clusters[ci]:
            r2 = recs[ri]
            store.conn.execute(f"UPDATE {r2.table} SET entity_id=? WHERE id=?", (new_id, r2.rowid))
        total_split += 1
    store.commit()
    print(f"  [{idx+1}/{len(merged)}] {disp} 记录{len(recs)} -> 拆出{len(clusters)-1}新簇 (累计{total_split})", flush=True)

# 重建图
G = build_graph(store)
save_graph(G)
n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
n_ent = G.number_of_nodes() - n_co
distinct_deg = {n: len(set(G.successors(n)) | set(G.predecessors(n))) for n in G}
top = sorted(distinct_deg.items(), key=lambda x: x[1], reverse=True)[:5]
max_deg = top[0][1] if top else 0
print(f"\n  重建图: {n_co}公司 + {n_ent}实体 = {G.number_of_nodes()}节点 {G.number_of_edges()}边")
print(f"  max-degree={max_deg}")
for n, d in top:
    nd = G.nodes[n]
    print(f"    {d}  {nd.get('kind','')}  {nd.get('name','') or nd.get('code','')}")
store.close()
