"""P1: 拆分刘伟(degree=45, common name hub) 降低福石控股度数。"""
import sys, json, time
from pathlib import Path
from dataclasses import dataclass
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.store.db import Store
from src.llm.client import LLMClient
from src.disambiguate.cluster import greedy_cluster
from src.disambiguate.resolver import resolve_pair
from src.disambiguate.signals import Record, Stats
from src.graph.store import build_graph, save_graph

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

# 先清理刘伟的旧#D实体
# 先清理刘伟的旧#D实体(reassign回parent后删)
for r in store.conn.execute("SELECT entity_id FROM entity WHERE canonical_name LIKE '刘伟#D%'").fetchall():
    # reassign records back to 刘伟
    parent = store.conn.execute("SELECT entity_id FROM entity WHERE canonical_name='刘伟' AND entity_type='person' AND is_channel=0 LIMIT 1").fetchone()
    if parent:
        store.conn.execute("UPDATE position SET entity_id=? WHERE entity_id=?", (parent[0], r[0]))
        store.conn.execute("UPDATE holding SET entity_id=? WHERE entity_id=?", (parent[0], r[0]))
store.conn.execute("DELETE FROM entity WHERE canonical_name LIKE '刘伟#D%'")
store.commit()

# 找 刘伟 entity
eid = store.conn.execute("SELECT entity_id FROM entity WHERE canonical_name='刘伟' AND entity_type='person' AND is_channel=0 AND canonical_name NOT LIKE '%#D%' LIMIT 1").fetchone()
if not eid:
    print("刘伟 not found"); store.close(); exit()
eid = eid[0]
recs = pull_records(store, eid, 150)
print(f"刘伟 entity_id={eid}, 记录={len(recs)}")

n_co = store.conn.execute("SELECT COUNT(DISTINCT stock_code) FROM (SELECT stock_code FROM position WHERE entity_id=? UNION SELECT stock_code FROM holding WHERE entity_id=?)", (eid, eid)).fetchone()[0]
stats = Stats(name_freq=len(recs), name_company_count=n_co)
print(f"  涉及 {n_co} 家公司")

llm_budget = [8]
def decider(i, rep_i):
    ra, rb = recs[rep_i], recs[i]
    ra_r = Record(stock_code=ra.stock_code, title=ra.title, valid_from=ra.valid_from, source=ra.source)
    rb_r = Record(stock_code=rb.stock_code, title=rb.title, valid_from=rb.valid_from, source=rb.source)
    use_llm = llm if llm_budget[0] > 0 else None
    if use_llm is not None:
        llm_budget[0] -= 1
    v = resolve_pair("刘伟", ra_r, rb_r, stats, use_llm)
    return v

clusters = greedy_cluster(len(recs), decider)
print(f"  拆分: {len(clusters)} 簇 (原1个)")
if len(clusters) <= 1:
    print("  无需拆分"); store.close(); exit()

for ci in range(1, len(clusters)):
    new_canonical = f"刘伟#D{ci+1}"
    note = f"P1 split from E:{eid} cluster{ci+1} (records={len(clusters[ci])})"
    raw_names = json.dumps(["刘伟"], ensure_ascii=False)
    cur = store.conn.execute(
        "INSERT INTO entity(entity_type, canonical_name, display_name, raw_names, is_channel, confidence, disambig_note) "
        "VALUES(?,?,?,?,0,'medium',?)",
        ('person', new_canonical, '刘伟', raw_names, note))
    new_id = int(cur.lastrowid)
    for ri in clusters[ci]:
        r = recs[ri]
        store.conn.execute(f"UPDATE {r.table} SET entity_id=? WHERE id=?", (new_id, r.rowid))
store.commit()

# 重建图
G = build_graph(store)
save_graph(G)
deg = {n: len(set(G.successors(n)) | set(G.predecessors(n))) for n in G}
top = sorted(deg.items(), key=lambda x: x[1], reverse=True)[:3]
print(f"\n重建图: {G.number_of_nodes()}节点 {G.number_of_edges()}边")
for n, d in top:
    nd = G.nodes[n]
    print(f"  max-degree={d} kind={nd.get('kind')} name={nd.get('name','') or nd.get('code','')}")
store.close()
