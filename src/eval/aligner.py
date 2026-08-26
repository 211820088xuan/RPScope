"""P5 对齐器 - 把系统候选与 gold_related_party 按名称对齐, 输出三分类。

matched: gold 名 ∩ 系统候选名
gold_only: gold 有, 系统未命中(可能是系统漏报 OR 合理未披露 OR 名称未对齐)
system_only: 系统发现, gold 未披露(可能真漏报[系统价值] OR 系统误报)

按名称(归一化)对齐, 不依赖 entity_id(因多数 gold 下游未映射)。
"""
from __future__ import annotations

from collections import defaultdict

from src.normalize.name import normalize_name, org_match_key
from src.rules.engine import RuleEngine
from src.store.db import Store


def norm_name(name: str) -> str:
    """统一归一: 先 org_match_key(剥后缀), 再 normalize。"""
    if not name:
        return ""
    return normalize_name(org_match_key(name)) or normalize_name(name)


def align_one(store: Store, engine: RuleEngine, stock_code: str, as_of: str | None = None) -> dict:
    # gold 名集
    gold_rows = store.get_gold(stock_code)
    gold_names = {norm_name(r["party_name"]) for r in gold_rows if r["party_name"]}
    gold_names.discard("")
    # 系统候选名集
    cands = engine.evaluate(store, stock_code, as_of)
    sys_names = {norm_name(c.party_name) for c in cands if c.party_name}
    sys_names.discard("")
    matched = gold_names & sys_names
    gold_only = gold_names - sys_names
    system_only = sys_names - gold_names
    return {"code": stock_code, "matched": matched, "gold_only": gold_only,
            "system_only": system_only, "n_gold": len(gold_names), "n_sys": len(sys_names),
            "cands": cands}


def align_batch(store: Store, engine: RuleEngine, codes: list[str]) -> dict:
    agg = defaultdict(list)
    for c in codes:
        r = align_one(store, engine, c)
        for k in ("matched", "gold_only", "system_only"):
            agg[k].extend([(c, n) for n in r[k]])
    return {"per_company": [align_one(store, engine, c) for c in codes],
            "matched": agg["matched"], "gold_only": agg["gold_only"], "system_only": agg["system_only"]}
