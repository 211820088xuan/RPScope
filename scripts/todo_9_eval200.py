"""#9: 重跑eval(203家) + 更新全部文档。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.store.db import Store
from src.rules.engine import RuleEngine
from src.eval.aligner import align_batch
from src.eval.metrics import prf

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")
codes = [r[0] for r in s.conn.execute("SELECT DISTINCT stock_code FROM gold_related_party").fetchall()]
print(f"gold 公司: {len(codes)}")

for label, sc in [("strict", None), ("comparable(upstream)", "upstream"), ("capability_out(downstream)", "downstream")]:
    r = align_batch(s, eng, codes, scope=sc)
    m = prf(len(r["matched"]), len(r["system_only"]), len(r["gold_only"]))
    print(f"  {label}: P={m['precision']*100:.1f}% R={m['recall']*100:.1f}% F1={m['f1']*100:.1f}% matched={m['tp']} sys={m['fp']} gold={m['fn']}")

# gold stats
print(f"\ngold 总计: {s.conn.execute('SELECT COUNT(*) FROM gold_related_party').fetchone()[0]} 条, {len(codes)} 家")
print(f"映射: {s.conn.execute('SELECT COUNT(*) FROM gold_related_party WHERE party_entity_id IS NOT NULL').fetchone()[0]}")
for r in s.conn.execute("SELECT scope_class, COUNT(*) n FROM gold_related_party GROUP BY scope_class").fetchall():
    print(f"  {r[0]}: {r[1]}")
s.close()
