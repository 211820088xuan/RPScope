"""P4 章节定位 - 用 pymupdf 缓存文本, 定位「关联方及关联交易」章节页范围。

优先 outline, 回退正文正则, 末回退散点。纯规则, 不用 LLM。
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from src.gold.pdf_text import get_all_text, n_pages

HEADER_PATTERNS = ["关联方及关联交易", "关联方情况", "关联方披露", "关联方关系"]
SECTION_BOUNDARY = re.compile(r"第[一二三四五六七八九十百]+节|^[一二三四五六七八九十百]+、|^\([一二三四五六七八九十百]+\)")


def _flatten_outline(pdf_path: str | Path) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception:
        return out
    try:
        toc = doc.get_toc()  # [[level, title, page], ...]
        for lvl, title, p in toc:
            out.append((str(title), p - 1))  # pymupdf page 1-indexed -> 0-indexed
    except Exception:
        pass
    doc.close()
    return out


def locate(pdf_path: str | Path) -> dict:
    n = n_pages(pdf_path)

    # 1. outline 优先
    for title, p in _flatten_outline(pdf_path):
        if any(pat in title for pat in HEADER_PATTERNS):
            end = n
            return {"found": True, "start": p, "end": end, "pages": list(range(p, min(end, n))),
                    "header": title, "method": "outline", "n_pages": n}

    # 2. 正文正则回退(跳过前 20 页封面/目录)
    txt = get_all_text(pdf_path)
    scan_start, scan_end = 20, min(n, 260)
    hits = []
    for pi in range(scan_start, scan_end):
        t = txt.get(pi, "")
        for line in t.splitlines():
            line = line.strip()
            if len(line) < 40 and any(pat in line for pat in HEADER_PATTERNS):
                hits.append(pi); break
    if hits:
        start = hits[0]
        end = min(start + 20, n)
        for pi in range(start + 1, scan_end):
            t = txt.get(pi, "")
            if pi > start and any(SECTION_BOUNDARY.match(l.strip()) for l in t.splitlines() if len(l.strip()) < 30):
                end = pi; break
            if pi >= start + 20:
                break
        return {"found": True, "start": start, "end": end, "pages": list(range(start, end)),
                "header": "关联方(正则)", "method": "regex", "n_pages": n}

    # 3. 散点回退: 收集含"关联方/关联交易"的页(上限 40)
    scatter = [pi for pi in range(scan_start, scan_end) if "关联方" in txt.get(pi, "") or "关联交易" in txt.get(pi, "")][:40]
    if scatter:
        return {"found": True, "start": scatter[0], "end": scatter[-1] + 1, "pages": scatter,
                "header": "关联方(散点)", "method": "scatter", "n_pages": n}

    return {"found": False, "start": None, "end": None, "pages": [], "header": "", "method": "none", "n_pages": n}
