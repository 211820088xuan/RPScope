"""P4 PDF 文本/表格缓存层 - pymupdf 实现。

pymupdf 比 pypdf 快且中文提取质量好(不缺字) + 支持表格抽取。
全页文本一次抽取缓存到 .cache/pdf_text/, 二次跑秒级。
"""
from __future__ import annotations

import pickle
import hashlib
from pathlib import Path

import pymupdf

CACHE_DIR = Path(".cache/pdf_text")


def _cache_path(pdf_path: str | Path) -> Path:
    p = Path(pdf_path)
    key = hashlib.sha1(str(p.resolve()).encode()).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{p.stem}_{key}.pkl"


def get_all_text(pdf_path: str | Path) -> dict[int, str]:
    """{page_index: text} 全页文本, 缓存。"""
    cp = _cache_path(pdf_path)
    if cp.exists():
        with open(cp, "rb") as f:
            return pickle.load(f)
    doc = pymupdf.open(str(pdf_path))
    out: dict[int, str] = {}
    for i in range(len(doc)):
        try:
            out[i] = doc[i].get_text("text") or ""
        except Exception:
            out[i] = ""
    doc.close()
    with open(cp, "wb") as f:
        pickle.dump(out, f, protocol=pickle.HIGHEST_PROTOCOL)
    return out


def get_tables(pdf_path: str | Path, page_idx: int) -> list[list[list[str]]]:
    """某页的表格列表, 每表 = [[row cells], ...]。"""
    doc = pymupdf.open(str(pdf_path))
    out: list[list[list[str]]] = []
    if 0 <= page_idx < len(doc):
        try:
            page = doc[page_idx]
            tabs = page.find_tables()
            for t in tabs:
                try:
                    out.append(t.extract())
                except Exception:
                    pass
        except Exception:
            pass
    doc.close()
    return out


def n_pages(pdf_path: str | Path) -> int:
    doc = pymupdf.open(str(pdf_path))
    n = len(doc)
    doc.close()
    return n
