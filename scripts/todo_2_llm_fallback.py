"""#2: LLM 兜底率(全图谱随机100对)。"""
import sys, time, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
random.seed(42)
from src.disambiguate.resolver import resolve_pair
from src.disambiguate.signals import Record, Stats
from src.llm.client import LLMClient
from src.store.db import Store

s = Store("rpscope.db")
pairs = list(s.conn.execute(
    "SELECT a.entity_id as a_id, b.entity_id as b_id, a.display_name as name, "
    "a.stock_code as a_code, b.stock_code as b_code, "
    "a.title as a_title, a.valid_from as a_vf, a.source as a_src, "
    "b.title as b_title, b.valid_from as b_vf, b.source as b_src "
    "FROM (SELECT p.entity_id, p.stock_code, p.title, p.valid_from, p.source, e.display_name "
    "      FROM position p JOIN entity e ON p.entity_id=e.entity_id "
    "      WHERE e.entity_type='person' AND e.is_channel=0 AND e.canonical_name NOT LIKE '%#D%') a "
    "JOIN (SELECT p.entity_id, p.stock_code, p.title, p.valid_from, p.source, e.display_name "
    "      FROM position p JOIN entity e ON p.entity_id=e.entity_id "
    "      WHERE e.entity_type='person' AND e.is_channel=0 AND e.canonical_name NOT LIKE '%#D%') b "
    "ON a.display_name = b.display_name AND a.entity_id < b.entity_id "
    "ORDER BY RANDOM() LIMIT 100"
).fetchall())

client = LLMClient()
llm_count = 0
for i, r in enumerate(pairs):
    ra = Record(stock_code=r["a_code"], title=r["a_title"], valid_from=r["a_vf"], source=r["a_src"])
    rb = Record(stock_code=r["b_code"], title=r["b_title"], valid_from=r["b_vf"], source=r["b_src"])
    n_co = s.conn.execute(
        "SELECT COUNT(DISTINCT stock_code) FROM position WHERE entity_id IN (?,?)",
        (r["a_id"], r["b_id"])).fetchone()[0]
    stats = Stats(name_freq=0, name_company_count=n_co)
    v = resolve_pair(r["name"], ra, rb, stats, client)
    if v.used_llm:
        llm_count += 1
    if (i + 1) % 20 == 0:
        print(f"  [{i+1}/100] LLM={llm_count}({llm_count/(i+1)*100:.0f}%)", flush=True)

n = len(pairs)
print(f"\n#2: 全图谱随机{n}对, LLM兜底={llm_count}({llm_count/n*100:.0f}%)")
print(f"  对照: 评测集71%(偏中段采样) vs 全图谱{llm_count/n*100:.0f}%")
s.close()
