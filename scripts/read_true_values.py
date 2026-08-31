"""读全部真值: P/R, scope, 三分类, 图统计。"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, ".")
from src.store.db import Store
from src.rules.engine import RuleEngine
from src.eval.aligner import align_batch
from src.eval.metrics import prf

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")
codes = [r[0] for r in s.conn.execute("SELECT DISTINCT stock_code FROM gold_related_party").fetchall()]

print("=== 真值(2026-08-24 修复政府控制人排除后) ===")
print(f"gold 公司: {len(codes)}")
print(f"gold 总条数: {s.conn.execute('SELECT COUNT(*) FROM gold_related_party').fetchone()[0]}")
print(f"映射成功: {s.conn.execute('SELECT COUNT(*) FROM gold_related_party WHERE party_entity_id IS NOT NULL').fetchone()[0]}")
print()

# scope 分布
for r in s.conn.execute("SELECT scope_class, COUNT(*) n FROM gold_related_party GROUP BY scope_class").fetchall():
    print(f"scope {r['scope_class']}: {r['n']}")

print()
# 三组口径
for label, sc in [("strict", None), ("comparable(upstream)", "upstream"), ("capability_out(downstream)", "downstream")]:
    r = align_batch(s, eng, codes, scope=sc)
    m = prf(len(r["matched"]), len(r["system_only"]), len(r["gold_only"]))
    print(f"{label}: P={m['precision']*100:.1f}% R={m['recall']*100:.1f}% F1={m['f1']*100:.1f}% matched={m['tp']} sys_only={m['fp']} gold_only={m['fn']}")

# 图统计
from src.graph.store import load_graph
G = load_graph()
n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
n_ent = G.number_of_nodes() - n_co
print(f"\n图: {n_co}公司 + {n_ent}实体 = {G.number_of_nodes()}节点 {G.number_of_edges()}边")
print(f"channel 实体: {s.conn.execute('SELECT COUNT(*) FROM entity WHERE is_channel=1').fetchone()[0]}")
print(f"event 总数: {s.conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]}")
print(f"llm_extracted: {s.conn.execute('SELECT COUNT(*) FROM event WHERE source_type=\"llm_extracted\"').fetchone()[0]}")
s.close()
