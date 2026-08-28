"""#2: LLM 兜底率 - 简化版(从 entity 表随机取同名对, 不做 position join)。"""
import sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
random.seed(42)
from src.disambiguate.signals import score_pair, Record, Stats
from src.store.db import Store

s = Store("rpscope.db")
# 从 entity 表找同名不同 entity 的对(随机100)
names = [r[0] for r in s.conn.execute(
    "SELECT canonical_name FROM entity WHERE entity_type='person' AND is_channel=0 "
    "AND canonical_name NOT LIKE '%#D%' GROUP BY canonical_name HAVING COUNT(*) > 1 LIMIT 500").fetchall()]
random.shuffle(names)
pairs = []
for name in names[:200]:
    ents = list(s.conn.execute(
        "SELECT entity_id, display_name FROM entity WHERE canonical_name=? AND entity_type='person' AND is_channel=0", (name,)).fetchall())
    if len(ents) >= 2:
        a, b = ents[0], ents[1]
        # 随机取两条 position 记录
        pa = s.conn.execute("SELECT stock_code, title, valid_from, source FROM position WHERE entity_id=? LIMIT 1", (a["entity_id"],)).fetchone()
        pb = s.conn.execute("SELECT stock_code, title, valid_from, source FROM position WHERE entity_id=? LIMIT 1", (b["entity_id"],)).fetchone()
        if pa and pb:
            pairs.append((name, pa, pb))

# 取前100对
pairs = pairs[:100]
high_same = 0; high_diff = 0; middle = 0
for name, pa, pb in pairs:
    ra = Record(stock_code=pa["stock_code"], title=pa["title"], valid_from=pa["valid_from"], source=pa["source"])
    rb = Record(stock_code=pb["stock_code"], title=pb["title"], valid_from=pb["valid_from"], source=pb["source"])
    n_co = 2
    stats = Stats(name_freq=0, name_company_count=n_co)
    score, parts, why = score_pair(name, ra, rb, stats)
    if score > 0.70:
        high_same += 1
    elif score < 0.40:
        high_diff += 1
    else:
        middle += 1

n = len(pairs)
print(f"#2: 全图谱随机{n}对(rule-only, 不调LLM)")
print(f"  规则同人(>0.70): {high_same} ({high_same/n*100:.0f}%)")
print(f"  规则不同人(<0.40): {high_diff} ({high_diff/n*100:.0f}%)")
print(f"  中段(需LLM): {middle} ({middle/n*100:.0f}%)")
print(f"  对照: 评测集71%(偏中段采样) vs 全图谱{middle/n*100:.0f}%")
s.close()
