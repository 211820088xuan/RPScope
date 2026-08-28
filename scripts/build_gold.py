"""P4 金标准构建 - 批量: 拿年报公告->下载PDF(缓存)->定位章节->抽取关联方->映射->落库。

PDF 下载限频+缓存; 每公司诚实记录成功/失败原因。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from src.data.akshare_client import AkshareClient
from src.gold.extractor import extract
from src.gold.mapper import log_unmapped, map_party_to_entity
from src.gold.section_locator import locate
from src.llm.client import LLMClient
from src.store.db import Store

PDF_DIR = Path(".cache/pdfs")


def get_annual_report_announcements(client: AkshareClient, stock_code: str) -> list[dict]:
    """拿该公司公告列表, 筛年报(标题含'年度报告'且不含摘要/英文版/更正)。"""
    df = client.get("stock_zh_a_disclosure_report_cninfo", symbol=stock_code,
                    market="沪深京", start_date="20230101", end_date="20261231")
    out = []
    for _, r in df.iterrows():
        title = str(r.get("公告标题", "")).strip()
        # 标题必须以"年度报告"结尾(=年报本身), 排除"半年度报告"/"关于...年度报告...说明会/公告"等周边
        if title.endswith("年度报告") and "半年度" not in title \
                and not any(x in title for x in ["摘要", "英文", "更正", "修订", "补丁", "H股"]):
            out.append({"title": title, "time": str(r.get("公告时间", "")),
                        "url": str(r.get("公告链接", ""))})
    out.sort(key=lambda x: x["time"], reverse=True)  # 最新在前
    return out


def _detail_to_pdf_url(detail_url: str, ann_time: str) -> str | None:
    """cninfo 详情页 URL -> static.cninfo.com.cn PDF URL。
    详情: .../disclosure/detail?...&announcementId=XXX&...&announcementTime=YYYY-MM-DD ...
    PDF: http://static.cninfo.com.cn/finalpage/{YYYY-MM-DD}/{announcementId}.PDF
    """
    import re
    mid = re.search(r"announcementId=(\d+)", detail_url)
    date = (ann_time or "")[:10]
    if mid and date:
        return f"http://static.cninfo.com.cn/finalpage/{date}/{mid.group(1)}.PDF"
    return None


def download_pdf(url: str, dest: Path, ann_time: str = "") -> bool:
    if dest.exists() and dest.stat().st_size > 10000:
        return True
    headers = {"User-Agent": "Mozilla/5.0"}
    # 优先: 详情页 -> static PDF URL
    candidates = []
    if "disclosure/detail" in url:
        pdfu = _detail_to_pdf_url(url, ann_time)
        if pdfu:
            candidates.append(pdfu)
    candidates.append(url)  # 原链接兜底(可能本就是 PDF)
    for u in candidates:
        try:
            resp = requests.get(u, timeout=90, headers=headers)
            if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                dest.write_bytes(resp.content)
                return True
        except Exception:
            continue
    return False


def build_one(store: Store, client: AkshareClient, llm: LLMClient, stock_code: str) -> dict:
    res = {"code": stock_code, "announcements": 0, "pdf_ok": False, "section_found": False,
           "n_parties": 0, "n_mapped": 0, "reason": "", "parties": [], "ann_url": "", "year": ""}
    anns = get_annual_report_announcements(client, stock_code)
    res["announcements"] = len(anns)
    if not anns:
        res["reason"] = "无年报公告"; return res
    ann = anns[0]
    year = ann["time"][:4]
    res["ann_url"] = ann["url"]; res["year"] = year
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    dest = PDF_DIR / f"{stock_code}_{year}.pdf"
    if not download_pdf(ann["url"], dest, ann.get("time", "")):
        res["reason"] = f"PDF下载失败 {ann['url'][:60]}"; return res
    res["pdf_ok"] = True
    loc = locate(dest)
    res["section_found"] = loc["found"]
    if not loc["found"]:
        res["reason"] = "章节定位失败"; return res
    parties = extract(dest, loc["pages"], llm, use_llm=True)
    res["parties"] = parties
    res["n_parties"] = len(parties)
    return res


def commit_one(store: Store, stock_code: str, parties: list[dict], ann_url: str, year: str) -> int:
    """主线程串行写库, 避 SQLite 并发锁。返回映射成功数。"""
    mapped = 0
    for p in parties:
        eid = map_party_to_entity(store, p["party_name"])
        if eid:
            mapped += 1
        else:
            log_unmapped(stock_code, p["party_name"])
        store.upsert_gold(stock_code=stock_code, report_year=int(year) if year.isdigit() else None,
                          party_name=p["party_name"], party_entity_id=eid,
                          relation_desc=p.get("relation_desc"), source_url=ann_url,
                          source_page=p.get("page"))
    return mapped


def main(codes: list[str] | None = None, n: int = 5, workers: int = 3) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    store = Store("rpscope.db")
    client = AkshareClient()
    llm = LLMClient()
    print(f"LLM enabled={llm.enabled} | 并行 {workers} worker", flush=True)
    if not codes:
        import random; random.seed()
        done = {r[0] for r in store.conn.execute(
            "SELECT DISTINCT stock_code FROM gold_related_party").fetchall()}
        pool = [r[0] for r in store.conn.execute(
            "SELECT DISTINCT stock_code FROM actual_controller").fetchall()]
        pool = [c for c in pool if c not in done]
        random.shuffle(pool)
        codes = pool[:n]
    force = "--force" in sys.argv
    if not force:
        codes = [c for c in codes if not store.conn.execute(
            "SELECT 1 FROM gold_related_party WHERE stock_code=? LIMIT 1", (c,)).fetchone()]
    print(f"构建金标准: {len(codes)} 家 {codes[:10]}{'...' if len(codes)>10 else ''}", flush=True)

    loc_ok = done = 0
    # 每个线程自己的 client/llm(避免共享 OpenAI client 跨线程)
    t0all = __import__("time").perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(build_one, Store("rpscope.db"), AkshareClient(), LLMClient(), c): c for c in codes}
        for fut in as_completed(futs):
            code = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                print(f"  {code}: ERROR {type(e).__name__}: {e}", flush=True); continue
            # 主线程串行写库
            if r["parties"]:
                r["n_mapped"] = commit_one(store, r["code"], r["parties"], r["ann_url"], r["year"])
                store.commit()
            if r["section_found"]:
                loc_ok += 1
            done += 1
            print(f"  {code}: pdf={r['pdf_ok']} section={r['section_found']} "
                  f"parties={r['n_parties']} mapped={r.get('n_mapped',0)} {r['reason']}", flush=True)
    dt = __import__("time").perf_counter() - t0all
    tot_cos = store.conn.execute("SELECT COUNT(DISTINCT stock_code) FROM gold_related_party").fetchone()[0]
    tot_p = store.conn.execute("SELECT COUNT(*) FROM gold_related_party").fetchone()[0]
    tot_m = store.conn.execute("SELECT COUNT(*) FROM gold_related_party WHERE party_entity_id IS NOT NULL").fetchone()[0]
    print(f"\n=== P4 累计 (gold 全量) ===", flush=True)
    print(f"覆盖 {tot_cos} 家 | 关联方 {tot_p} | 映射 {tot_m} ({tot_m/tot_p*100 if tot_p else 0:.0f}%)")
    print(f"本轮 {done} 家 | 章节定位 {loc_ok}/{done} | 耗时 {dt:.0f}s ({dt/max(done,1):.0f}s/家)")
    store.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    codes = args if args else None
    main(codes=codes, n=30)
