"""#2: LLM 兜底率 - 从 entity 内部取记录对(不跨 entity)。"""
import sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
random.seed(42)
from src.disambiguate.signals import score_pair, Record, Stats
from src.disambiguate.resolver import HIGH_SAME, LOW_DIFF
from src.store.db import Store

s = Store("rpscope.db")
# 找有 2+ 条 position 记录的 person entity
ents = list(s.conn.execute(
    "SELECT entity_id, display_name, canonical_name FROM entity "
    "WHERE entity_type='person' AND is_channel=0 AND canonical_name NOT LIKE '%#D%'").fetchall())
random.shuffle(ents)

high_same = 0; high_diff = 0; middle = 0; total = 0
for e in ents:
    if total >= 100:
        break
    recs = list(s.conn.execute(
        "SELECT stock_code, title, valid_from, source FROM position WHERE entity_id=? LIMIT 2", (e["entity_id"],)).fetchall())
    if len(recs) < 2:
        continue
    a, b = recs[0], recs[1]
    ra = Record(stock_code=a["stock_code"], title=a["title"], valid_from=a["valid_from"], source=a["source"])
    rb = Record(stock_code=b["stock_code"], title=b["title"], valid_from=b["valid_from"], source=b["source"])
    n_co = s.conn.execute(
        "SELECT COUNT(DISTINCT stock_code) FROM position WHERE entity_id=?", (e["entity_id"],)).fetchone()[0]
    stats = Stats(name_freq=0, name_company_count=n_co)
    score, parts, why = score_pair(e["display_name"], ra, rb, stats)
    if score > HIGH_SAME:
        high_same += 1
    elif score < LOW_DIFF:
        high_diff += 1
    else:
        middle += 1
    total += 1

print(f"#2: 全图谱随机{total}对(rule-only, 不调LLM)")
print(f"  规则同人(>{HIGH_SAME}): {high_same} ({high_same/total*100:.0f}%)")
print(f"  规则不同人(<{LOW_DIFF}): {high_diff} ({high_diff/total*100:.0f}%)")
print(f"  中段(需LLM): {middle} ({middle/total*100:.0f}%)")
print(f"  对照: 评测集71%(偏中段采样) vs 全图谱{middle/total*100:.0f}%")
s.close()
