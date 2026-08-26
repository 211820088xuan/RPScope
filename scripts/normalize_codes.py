"""一次性规范化: 把 position/company 里带 SH/SZ/BJ 前缀的 stock_code 转成 6 位裸码。
修 P3 发现的 inner_trade 前缀 bug。然后重建图。
"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.store.db import Store
from src.graph.store import build_graph, save_graph


def bare(code: str) -> str:
    c = re.sub(r"^[A-Za-z]+", "", str(code)).strip()
    return c.zfill(6)


store = Store("rpscope.db")
# 1. position: 带前缀 -> 裸码; 若裸码行已存在则删前缀行(去重, 避 UNIQUE 冲突)
rows = list(store.conn.execute(
    "SELECT id, entity_id, stock_code, title, valid_from FROM position "
    "WHERE substr(stock_code,1,2) IN ('SH','SZ','BJ')"))
upd = deldup = 0
for r in rows:
    b = bare(r["stock_code"])
    dup = store.conn.execute(
        "SELECT 1 FROM position WHERE entity_id=? AND stock_code=? AND title=? AND "
        "COALESCE(valid_from,'')=COALESCE(?,'') AND id<>?",
        (r["entity_id"], b, r["title"], r["valid_from"], r["id"])).fetchone()
    if dup:
        store.conn.execute("DELETE FROM position WHERE id=?", (r["id"],))
        deldup += 1
    else:
        store.conn.execute("UPDATE position SET stock_code=? WHERE id=?", (b, r["id"]))
        upd += 1
print(f"position: 改名 {upd}, 去重删 {deldup}")

# 2. company: 带前缀的, 若裸码已存在则删除前缀孤儿, 否则改名为裸码
crows = list(store.conn.execute(
    "SELECT stock_code FROM company WHERE substr(stock_code,1,2) IN ('SH','SZ','BJ')"))
deleted = renamed = 0
for r in crows:
    pre = r["stock_code"]; b = bare(pre)
    exist = store.conn.execute("SELECT 1 FROM company WHERE stock_code=?", (b,)).fetchone()
    if exist:
        store.conn.execute("DELETE FROM company WHERE stock_code=?", (pre,))
        deleted += 1
    else:
        store.conn.execute("UPDATE company SET stock_code=? WHERE stock_code=?", (b, pre))
        renamed += 1
print(f"company: 删除前缀孤儿 {deleted}, 改名 {renamed}")
store.commit()

# 3. 删可能的外键孤儿(position 指向已删 company 的) - 实际 position 已规范化到裸码, 应都命中
orphan = store.conn.execute(
    "SELECT COUNT(*) FROM position p LEFT JOIN company c ON p.stock_code=c.stock_code WHERE c.stock_code IS NULL").fetchone()[0]
print(f"position 孤儿(指向不存在公司): {orphan}")

# 4. 重建图
G = build_graph(store)
save_graph(G)
n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
print(f"重建图: 公司{n_co} 实体{G.number_of_nodes()-n_co} 边{G.number_of_edges()}")
