"""P8 构建 QA 测试集 - 自动生成有金答案的三类, open_qa 占位。

fact_query: 从图谱取公司, 问股东/实控人, 金=持有方名集
related_party: 从 gold_related_party 取公司, 金=年报披露关联方名集
relation_explain: 同实控人兄弟对(正) + 随机非兄弟对(负), 金=bool
open_qa: 占位(需人工补金答案)
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.store.db import Store

OUT = Path("data/eval/qa.jsonl")
random.seed(42)


def main() -> None:
    store = Store("rpscope.db")
    qa: list[dict] = []
    qid = 0

    # --- fact_query: 取有股东+实控人的公司 ---
    co_with_ctrl = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT stock_code FROM actual_controller").fetchall()][:30]
    for code in co_with_ctrl:
        # 金: 股东名集(非通道)
        holders = [r[0] for r in store.conn.execute(
            "SELECT e.display_name FROM holding h JOIN entity e ON h.entity_id=e.entity_id "
            "WHERE h.stock_code=? AND e.is_channel=0 AND e.display_name IS NOT NULL "
            "AND h.source='stock_gdfx_free_holding_detail_em' LIMIT 5", (code,)).fetchall()]
        if not holders:
            continue
        qid += 1
        qa.append({"id": f"q{qid:03d}", "intent": "fact_query", "code": code,
                   "question": f"{code}的前十大股东是谁",
                   "gold": {"type": "names", "expected": holders, "min_match": 1}})
        # 实控人
        ctrl = [r[0] for r in store.conn.execute(
            "SELECT e.display_name FROM actual_controller ac JOIN entity e ON ac.entity_id=e.entity_id "
            "WHERE ac.stock_code=? AND e.is_channel=0 AND e.display_name IS NOT NULL", (code,)).fetchall()]
        if ctrl:
            qid += 1
            qa.append({"id": f"q{qid:03d}", "intent": "fact_query", "code": code,
                       "question": f"{code}的实控人是谁", "gold": {"type": "names", "expected": ctrl, "min_match": 1}})

    # --- related_party: 取有 gold 的公司, 金=gold_related_party 名集 ---
    gold_cos = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT stock_code FROM gold_related_party").fetchall()][:30]
    for code in gold_cos:
        names = [r[0] for r in store.conn.execute(
            "SELECT party_name FROM gold_related_party WHERE stock_code=?", (code,)).fetchall()]
        if not names:
            continue
        qid += 1
        qa.append({"id": f"q{qid:03d}", "intent": "related_party", "code": code,
                   "question": f"{code}的关联方有哪些", "gold": {"type": "names", "expected": names, "min_match": 1}})

    # --- relation_explain: 同实控人兄弟(正) + 随机非兄弟(负) ---
    # 按 controller 分组, 取同组对(正)
    groups: dict = {}
    for r in store.conn.execute(
            "SELECT entity_id, stock_code FROM actual_controller").fetchall():
        groups.setdefault(r[0], []).append(r[1])
    pos_pairs = []
    for eid, cos in groups.items():
        if len(cos) >= 2:
            for i in range(min(len(cos) - 1, 1)):  # 每组取1对
                pos_pairs.append((cos[i], cos[i + 1]))
        if len(pos_pairs) >= 10:
            break
    for a, b in pos_pairs[:10]:
        qid += 1
        qa.append({"id": f"q{qid:03d}", "intent": "relation_explain", "code": a,
                   "question": f"{a}和{b}是什么关系", "gold": {"type": "bool", "expected": True}})

    # 负对: 同 controller 池里随机两两不同组
    all_cos = [c for cs in groups.values() for c in cs]
    neg_pairs = []
    tries = 0
    while len(neg_pairs) < 10 and tries < 200:
        a, b = random.sample(all_cos, 2)
        # 不同 controller
        ca = store.conn.execute("SELECT entity_id FROM actual_controller WHERE stock_code=?", (a,)).fetchall()
        cb = store.conn.execute("SELECT entity_id FROM actual_controller WHERE stock_code=?", (b,)).fetchall()
        if ca and cb and ca[0][0] != cb[0][0]:
            neg_pairs.append((a, b))
        tries += 1
    for a, b in neg_pairs:
        qid += 1
        qa.append({"id": f"q{qid:03d}", "intent": "relation_explain", "code": a,
                   "question": f"{a}和{b}是什么关系", "gold": {"type": "bool", "expected": False}})

    # --- open_qa 占位(需人工补金答案) ---
    for code in gold_cos[:5]:
        qid += 1
        qa.append({"id": f"q{qid:03d}", "intent": "open_qa", "code": code,
                   "question": f"{code}有哪些风险事件", "gold": {"type": "manual", "expected": ""}})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for q in qa:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    by = {}
    for q in qa:
        by[q["intent"]] = by.get(q["intent"], 0) + 1
    print(f"QA 集 {len(qa)} 条 -> {OUT}")
    print(f"  " + " | ".join(f"{k}:{v}" for k, v in by.items()))
    store.close()


if __name__ == "__main__":
    main()
