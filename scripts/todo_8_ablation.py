"""#8: 完整消融(4组: 无R1/无R2/无R3/无R4, 可比口径, 203家)。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.store.db import Store
from src.rules.engine import RuleEngine
from src.eval.aligner import align_batch
from src.eval.metrics import prf

s = Store("rpscope.db")
codes = [r[0] for r in s.conn.execute("SELECT DISTINCT stock_code FROM gold_related_party").fetchall()]
print(f"#8: 消融(203家, 可比口径)")

configs = [
    ("基线(全开)", None),
    ("无R1(无直接持股)", "R1"),
    ("无R2(无同一控制)", "R2"),
    ("无R3(无共同股东)", "R3"),
    ("无R4(无连锁董事)", "R4"),
]
for label, disable in configs:
    eng = RuleEngine("config/rules.yaml")
    if disable:
        eng.rules = [r for r in eng.rules if r.rule_id != disable]
    r = align_batch(s, eng, codes, scope="upstream")
    m = prf(len(r["matched"]), len(r["system_only"]), len(r["gold_only"]))
    print(f"  {label}: P={m['precision']*100:.1f}% R={m['recall']*100:.1f}% matched={m['tp']} sys={m['fp']}")
s.close()
