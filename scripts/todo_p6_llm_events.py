"""P6 LLM事件抽取实跑 - 从已缓存的年报PDF关联方章节文本抽事件。"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.store.db import Store
from src.llm.client import LLMClient
from src.extract.event_extractor import extract_events
from src.gold.pdf_text import get_all_text
from src.gold.section_locator import locate

store = Store("rpscope.db")
client = LLMClient()

# 找3家有PDF缓存的公司
codes_with_pdf = []
for p in Path(".cache/pdfs").glob("*.pdf"):
    code = p.stem.split("_")[0]
    if code not in codes_with_pdf:
        codes_with_pdf.append(code)
codes_with_pdf = codes_with_pdf[:3]
print(f"P6: LLM事件抽取实跑({len(codes_with_pdf)}家: {codes_with_pdf})")

total_events = 0
for code in codes_with_pdf:
    pdf = next(Path(".cache/pdfs").glob(f"{code}_*.pdf"), None)
    if not pdf:
        print(f"  {code}: 无PDF"); continue
    loc = locate(pdf)
    if not loc["found"]:
        print(f"  {code}: 章节定位失败"); continue
    pages_text = get_all_text(pdf)
    full = "\n".join(pages_text.get(pi, "") for pi in loc["pages"])[:4000]
    events = extract_events(full, client, source_url=str(pdf), page=loc["pages"][0] if loc["pages"] else None)
    print(f"  {code}: 抽出 {len(events)} 个事件", flush=True)
    for e in events[:5]:
        print(f"    {e['event_type']} | {e.get('counterparty','')[:20]} | {e.get('summary','')[:40]}")
        # 入库
        store.upsert_event(
            event_type=e["event_type"], subject_code=code,
            counterparty=e.get("counterparty"), amount=e.get("amount"),
            summary=e.get("summary"), event_date=e.get("event_date"),
            source_type="llm_extracted", source_url=str(pdf),
            extract_conf="glm-5.2")
        total_events += 1
    time.sleep(2)

store.commit()
n = store.conn.execute("SELECT COUNT(*) FROM event WHERE source_type='llm_extracted'").fetchone()[0]
print(f"\n总计: 抽出 {total_events} 个事件, event表 llm_extracted={n}条")
store.close()
