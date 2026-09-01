"""T1+T2: 词典匹配 — 从 DB 构建公司/人名词典, 最长匹配定位实体。

优先级: 股票代码精确 > 词典最长匹配 > 正则 > LLM 兜底
歧义(多匹配) → 走澄清机制, 不自选。
"""
from __future__ import annotations
import re, sqlite3, unicodedata
from typing import NamedTuple


class Match(NamedTuple):
    text: str           # 匹配到的原文
    stock_code: str = ""
    entity_id: int = 0
    entity_type: str = ""  # company / person / org
    method: str = ""       # code_exact / dict_short_name / dict_full_name / dict_person
    candidates: list = []  # 歧义时列出候选
    ambiguous: bool = False


def _norm(s: str) -> str:
    """归一化: 去空格, 全半角统一, 去 A/B 后缀标记。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace(" ", "").replace("\u3000", "").strip()
    s = re.sub(r"[ＡＢＣＤ]$", "", s)
    return s.lower()


class CompanyMatcher:
    """公司名词典: short_name / full_name → stock_code, 最长匹配。"""

    def __init__(self, conn: sqlite3.Connection):
        self._by_name: dict[str, list[dict]] = {}  # normalized_name → [{code, name}]
        self._by_code: dict[str, dict] = {}  # code → {code, name}
        for r in conn.execute("SELECT stock_code, short_name, full_name FROM company").fetchall():
            code = r["stock_code"]
            entry = {"code": code, "name": r["short_name"]}
            self._by_code[code] = entry
            for name in (r["short_name"], r["full_name"]):
                if not name:
                    continue
                n = _norm(name)
                if len(n) < 2:
                    continue
                self._by_name.setdefault(n, []).append(entry)
        # 按 name 长度降序(最长优先匹配)
        self._sorted_names = sorted(self._by_name.keys(), key=len, reverse=True)

    def match(self, text: str) -> Match | None:
        """在 text 中查找公司名, 返回最长匹配。歧义时返回 ambiguous。"""
        text_norm = _norm(text)
        # 1. 股票代码精确匹配
        m = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        if m:
            code = m.group(1)
            if code in self._by_code:
                return Match(text=code, stock_code=code, entity_type="company",
                             method="code_exact", candidates=[], ambiguous=False)
        # 2. 词典最长匹配
        hits = []
        for name in self._sorted_names:
            if name in text_norm:
                hits.append((name, self._by_name[name]))
                break  # 最长优先, 第一个就是最长的
        if not hits:
            return None
        name_key, entries = hits[0]
        # 找原文中对应的子串(非归一化)
        # 在原文中搜索匹配归一化后的 name
        matched_text = ""
        for i in range(len(text)):
            sub = _norm(text[i:])
            if sub.startswith(name_key):
                matched_text = text[i:i+len(name_key)+_extra_len(text[i:], name_key)]
                break
        if not matched_text:
            matched_text = text  # fallback
        if len(entries) == 1:
            return Match(text=matched_text, stock_code=entries[0]["code"],
                         entity_type="company", method="dict_" + ("short_name" if len(name_key) <= 8 else "full_name"),
                         candidates=[], ambiguous=False)
        # 多匹配 → 歧义
        return Match(text=matched_text, stock_code="", entity_type="company",
                     method="dict_ambiguous", candidates=entries, ambiguous=True)

    def all_matches(self, text: str) -> list[Match]:
        """找 text 中所有公司名(用于 Q2 双实体, Q6 双公司), 按文本位置排序(左到右)。"""
        text_norm = _norm(text)
        # 找所有匹配: (position, name, entries)
        found = []
        for name in self._sorted_names:
            idx = 0
            while True:
                pos = text_norm.find(name, idx)
                if pos < 0:
                    break
                idx = pos + 1
                found.append((pos, name))
        if not found:
            return []
        # 按位置排序, 去重叠(保留最长的)
        found.sort(key=lambda x: x[0])
        results = []
        last_end = -1
        for pos, name in found:
            if pos < last_end:
                continue  # 与已选区域重叠
            last_end = pos + len(name)
            entries = self._by_name[name]
            matched_text = text[pos:pos+len(name)]
            if len(entries) == 1:
                results.append(Match(text=matched_text, stock_code=entries[0]["code"],
                                     entity_type="company", method="dict_match",
                                     candidates=[], ambiguous=False))
            else:
                results.append(Match(text=matched_text, stock_code="",
                                     entity_type="company", method="dict_ambiguous",
                                     candidates=entries, ambiguous=True))
            if len(results) >= 2:
                break
        return results


def _extra_len(original: str, norm_key: str) -> int:
    """原文和归一化后的长度差(空格等)。简化: 0。"""
    return 0


class PersonMatcher:
    """人名词典: entity 表 entity_type=person, 最长匹配。"""

    def __init__(self, conn: sqlite3.Connection):
        self._by_name: dict[str, list[dict]] = {}
        for r in conn.execute(
            "SELECT entity_id, display_name, canonical_name FROM entity "
            "WHERE entity_type='person' AND is_channel=0 AND display_name IS NOT NULL"
        ).fetchall():
            name = _norm(r["display_name"])
            if len(name) < 2:
                continue
            entry = {"entity_id": r["entity_id"], "name": r["display_name"]}
            self._by_name.setdefault(name, []).append(entry)
        self._sorted_names = sorted(self._by_name.keys(), key=len, reverse=True)

    def match(self, text: str) -> Match | None:
        """在 text 中查找人名, 最长匹配。重名 → ambiguous。"""
        text_norm = _norm(text)
        for name in self._sorted_names:
            if name in text_norm:
                entries = self._by_name[name]
                matched_text = text[text_norm.find(name):text_norm.find(name)+len(name)]
                if len(entries) == 1:
                    return Match(text=matched_text, entity_id=entries[0]["entity_id"],
                                 entity_type="person", method="dict_person",
                                 candidates=[], ambiguous=False)
                return Match(text=matched_text, entity_id=0, entity_type="person",
                             method="dict_person_ambiguous", candidates=entries, ambiguous=True)
        return None
