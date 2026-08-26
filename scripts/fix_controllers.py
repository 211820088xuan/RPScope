"""清理占位控制人(无/不详/...)并重灌实控人。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data.akshare_client import AkshareClient
from src.data.ingest import EntityCache, ingest_controllers, load_channel_cfg
from src.store.db import Store
from src.graph.store import build_graph, save_graph

store = Store("rpscope.db")
PLACEHOLDERS = {"无", "无实际控制人", "不详", "未知", "不适用", "—", "-", "无实际控制", "无实控人", "空"}

# 1. 清空 actual_controller
store.conn.execute("DELETE FROM actual_controller")
print("cleared actual_controller")

# 2. 删除仅作占位控制人、且无持股/任职记录的实体
ph_list = ",".join("?" for _ in PLACEHOLDERS)
rows = list(store.conn.execute(
    f"SELECT entity_id FROM entity WHERE display_name IN ({ph_list})", list(PLACEHOLDERS)))
deleted = 0
for r in rows:
    eid = r[0]
    npos = store.conn.execute("SELECT COUNT(*) FROM position WHERE entity_id=?", (eid,)).fetchone()[0]
    nhold = store.conn.execute("SELECT COUNT(*) FROM holding WHERE entity_id=?", (eid,)).fetchone()[0]
    if npos == 0 and nhold == 0:
        store.conn.execute("DELETE FROM entity WHERE entity_id=?", (eid,))
        deleted += 1
store.commit()
print(f"deleted {deleted} placeholder-only entities")

# 3. 重灌实控人(已修复占位过滤)
client = AkshareClient()
exact, pats = load_channel_cfg()
ec = EntityCache(store)
existing_cos = {r[0] for r in store.conn.execute("SELECT stock_code FROM company")}
n = ingest_controllers(store, client, ec, existing_cos)
store.commit()
print(f"re-ingested controllers: {n}")

# 4. 重建图
G = build_graph(store)
save_graph(G)
n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
n_ent = G.number_of_nodes() - n_co
print(f"graph: 公司{n_co} 实体{n_ent} 边{G.number_of_edges()}")
