"""P4 映射 - 把抽取的关联方名称映射到 entity 表(复用 normalize org_match_key)。

映射成功的记 party_entity_id; 失败的写 data/gold_unmapped.csv 供人工。
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.normalize.name import fund_match_key, normalize_name, org_match_key

UNMAPPED_CSV = Path("data/gold_unmapped.csv")


def map_party_to_entity(store, party_name: str) -> int | None:
    """按 canonical_name 多策略匹配 entity。返回 entity_id 或 None。"""
    name = party_name.strip()
    if not name:
        return None
    # 候选匹配键(机构用 org_match_key, 也试 normalize_name)
    keys = []
    if any(k in name for k in ["基金", "资管", "计划"]):
        keys.append(fund_match_key(name))
    keys.append(org_match_key(name))
    keys.append(normalize_name(name))
    keys.append(name)
    for k in dict.fromkeys(keys):  # 去重保序
        if not k:
            continue
        r = store.conn.execute(
            "SELECT entity_id FROM entity WHERE canonical_name=? COLLATE NOCASE", (k,)).fetchone()
        if r:
            return int(r[0])
    return None


def log_unmapped(stock_code: str, party_name: str) -> None:
    UNMAPPED_CSV.parent.mkdir(parents=True, exist_ok=True)
    exists = UNMAPPED_CSV.exists()
    with open(UNMAPPED_CSV, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["stock_code", "party_name"])
        w.writerow([stock_code, party_name])
