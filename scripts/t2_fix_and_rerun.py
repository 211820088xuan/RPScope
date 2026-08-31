"""T2: 修复前后指标对照 + 重跑channel + rebuild_graph。"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.store.db import Store
from src.rules.engine import RuleEngine
from src.eval.aligner import align_batch
from src.eval.metrics import prf

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")
codes = [r[0] for r in s.conn.execute("SELECT DISTINCT stock_code FROM gold_related_party").fetchall()]

# === 修复前(用旧排除, 但代码已更新; 需先重标记才能看变化) ===
# 先记录当前(修复前)的 channel 数
ch_before = s.conn.execute("SELECT COUNT(*) FROM entity WHERE is_channel=1").fetchone()[0]
print(f"=== 修复前 ===")
print(f"  channel 实体: {ch_before}")

# 跑当前指标(排除规则已更新但 is_channel 还没重标记, 所以这是修复前)
for label, sc in [("strict", None), ("comparable(upstream)", "upstream"), ("capability_out(downstream)", "downstream")]:
    r = align_batch(s, eng, codes, scope=sc)
    m = prf(len(r["matched"]), len(r["system_only"]), len(r["gold_only"]))
    print(f"  {label}: P={m['precision']*100:.1f}% R={m['recall']*100:.1f}% matched={m['tp']} sys={m['fp']} gold={m['fn']}")

# R2 单独(前50家)
r2_before = 0
for code in codes[:50]:
    cands = eng.evaluate(s, code)
    r2_before += sum(1 for c in cands if "R2" in c.rule_id)
print(f"  R2候选(前50家): {r2_before}")

# === 重标记 channel ===
print(f"\n=== 重跑 channel 标记 ===")
from src.normalize.name import is_channel_name
import yaml, re
cfg = yaml.safe_load(Path("config/rules.yaml").read_text(encoding="utf-8"))["channel_exclusion"]
exact = set(cfg.get("exact", []))
pats = [re.compile(p) for p in cfg.get("patterns", [])]

rows = list(s.conn.execute("SELECT entity_id, display_name, raw_names FROM entity"))
flagged = 0
for r in rows:
    raws = json.loads(r["raw_names"] or "[]") if r["raw_names"] else []
    names = [r[1] or ""] + raws
    ch = any(is_channel_name(str(n), exact, pats) for n in names if n)
    if ch:
        s.conn.execute("UPDATE entity SET is_channel=1 WHERE entity_id=?", (r[0],))
        flagged += 1
    else:
        s.conn.execute("UPDATE entity SET is_channel=0 WHERE entity_id=?", (r[0],))
s.commit()
ch_after = s.conn.execute("SELECT COUNT(*) FROM entity WHERE is_channel=1").fetchone()[0]
print(f"  标记 channel: {ch_after} (修复前 {ch_before}, 变化 {ch_after - ch_before:+d})")

# === 重建图 ===
from src.graph.store import build_graph, save_graph
G = build_graph(s)
save_graph(G)
n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
print(f"  重建图: {n_co}公司 + {G.number_of_nodes()-n_co}实体 = {G.number_of_nodes()}节点 {G.number_of_edges()}边")

# === 修复后指标 ===
print(f"\n=== 修复后 ===")
for label, sc in [("strict", None), ("comparable(upstream)", "upstream"), ("capability_out(downstream)", "downstream")]:
    r = align_batch(s, eng, codes, scope=sc)
    m = prf(len(r["matched"]), len(r["system_only"]), len(r["gold_only"]))
    print(f"  {label}: P={m['precision']*100:.1f}% R={m['recall']*100:.1f}% matched={m['tp']} sys={m['fp']} gold={m['fn']}")

r2_after = 0
for code in codes[:50]:
    cands = eng.evaluate(s, code)
    r2_after += sum(1 for c in cands if "R2" in c.rule_id)
print(f"  R2候选(前50家): {r2_after} (修复前 {r2_before}, 变化 {r2_after - r2_before:+d})")

s.close()
