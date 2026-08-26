"""金标准能力范围分类器 - upstream/downstream/other。

基于 relation_desc + party_name 关键词匹配, 不用 LLM。
规则在 config/scope_rules.yaml, 可审计。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

_RULES: dict | None = None


def _load_rules() -> dict:
    global _RULES
    if _RULES is None:
        p = Path("config/scope_rules.yaml")
        if not p.exists():
            p = Path(__file__).resolve().parent.parent.parent / "config" / "scope_rules.yaml"
        _RULES = yaml.safe_load(p.read_text(encoding="utf-8"))
    return _RULES


def _match_any(text: str, patterns: list[str]) -> bool:
    """text 是否匹配 patterns 中任一正则(不区分大小写)。"""
    if not text:
        return False
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def classify(party_name: str, relation_desc: str | None = None) -> str:
    """返回 upstream / downstream / other。

    优先在 relation_desc 里匹配; 不中则在 party_name 里兜底。
    downstream 优先于 upstream(更具体的先判)。
    """
    rules = _load_rules()
    desc = relation_desc or ""
    name = party_name or ""

    # 1. relation_desc 优先
    if desc:
        if _match_any(desc, rules["downstream"]["desc_keywords"]):
            return "downstream"
        if _match_any(desc, rules["upstream"]["desc_keywords"]):
            return "upstream"

    # 2. party_name 兜底(仅 relation_desc 空时)
    if not desc and name:
        if _match_any(name, rules["downstream"]["name_keywords"]):
            return "downstream"
        # party_name 含人名特征: 短(<=4字)且无公司后缀 → 可能是上游人(董事/股东)
        has_suffix = any(k in name for k in ["公司", "集团", "企业", "基金", "银行", "证券"])
        if len(name) <= 4 and not has_suffix:
            return "upstream"

    return "other"


def classify_batch(store) -> dict:
    """对 gold_related_party 全表分类, UPDATE scope_class, 返回分布统计。"""
    # 确保字段存在
    try:
        store.conn.execute("SELECT scope_class FROM gold_related_party LIMIT 1")
    except Exception:
        store.conn.execute("ALTER TABLE gold_related_party ADD COLUMN scope_class TEXT")
        store.commit()

    rows = store.conn.execute("SELECT id, party_name, relation_desc FROM gold_related_party").fetchall()
    counts = {"upstream": 0, "downstream": 0, "other": 0}
    for r in rows:
        sc = classify(r["party_name"], r["relation_desc"])
        store.conn.execute("UPDATE gold_related_party SET scope_class=? WHERE id=?", (sc, r["id"]))
        counts[sc] += 1
    store.commit()
    return counts
