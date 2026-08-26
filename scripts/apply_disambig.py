"""P2 应用消歧 - 找高合并人名实体, 按记录聚类拆分, 重assign 记录, 重建图。

只处理记录数>阈值的高合并人名(通常单字/常见姓); 拆分后图最高度数应降到<100。
LLM 调用按人封顶(默认30次/人), 超出纯规则判定。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.disambiguate.cluster import greedy_cluster
from src.disambiguate.resolver import resolve_pair
from src.disambiguate.signals import Record, Stats
from src.graph.store import build_graph, save_graph
from src.llm.client import LLMClient
from src.store.db import Store


@dataclass
class Rec:
    table: str
    rowid: int
    stock_code: str
    title: str
    valid_from: str
    source: str


def pull_records(store: Store, entity_id: int, limit: int = 150) -> list[Rec]:
    rows = list(store.conn.execute(
        "SELECT 'position' t, id, stock_code, title, valid_from, source FROM position WHERE entity_id=? "
        "UNION ALL SELECT 'holding', id, stock_code, '', valid_from, source FROM holding WHERE entity_id=? "
        "LIMIT ?",
        (entity_id, entity_id, limit)))
    return [Rec(r[0], r[1], r[2] or "", r[3] or "", r[4] or "", r[5] or "") for r in rows]


def split_entity(store: Store, entity_id: int, canonical: str, display: str,
                 client: LLMClient, max_llm_per_person: int = 15) -> int:
    """拆分一个高合并人名实体。返回拆出的新簇数(不含原簇)。"""
    recs = pull_records(store, entity_id)
    if len(recs) < 5:
        return 0
    # 全局统计: 该 canonical 关联多少公司
    name_company_count = int(store.conn.execute(
        "SELECT COUNT(DISTINCT stock_code) FROM ("
        "  SELECT stock_code FROM position WHERE entity_id=? "
        "  UNION SELECT stock_code FROM holding WHERE entity_id=?)",
        (entity_id, entity_id)).fetchone()[0])
    stats = Stats(name_freq=len(recs), name_company_count=name_company_count)

    llm_budget = [max_llm_per_person]

    def make_decider(recs_list: list[Rec]):
        def decider(i: int, rep_i: int):
            ra, rb = recs_list[rep_i], recs_list[i]
            # 用 Record(信号层) 复用
            ra_r = Record(stock_code=ra.stock_code, title=ra.title, valid_from=ra.valid_from, source=ra.source)
            rb_r = Record(stock_code=rb.stock_code, title=rb.title, valid_from=rb.valid_from, source=rb.source)
            # 预算用尽 -> 用无 LLM 解析(中段保守判不同人)
            use_llm = client if llm_budget[0] > 0 else None
            if use_llm is not None:
                llm_budget[0] -= 1  # 预扣; resolve_pair 只在中段才真正调
            v = resolve_pair(display, ra_r, rb_r, stats, use_llm)
            return v
        return decider

    clusters = greedy_cluster(len(recs), make_decider(recs))
    if len(clusters) <= 1:
        return 0

    # 第 0 簇保留原 entity_id; 其余簇各建新实体并 reassign 记录
    import json as _json
    for ci in range(1, len(clusters)):
        new_canonical = f"{canonical}#D{ci + 1}"
        note = f"split from E:{entity_id} cluster{ci + 1} (records={len(clusters[ci])})"
        raw_names = _json.dumps([display], ensure_ascii=False)
        cur = store.conn.execute(
            "INSERT INTO entity(entity_type, canonical_name, display_name, raw_names, is_channel, confidence, disambig_note) "
            "VALUES(?,?,?,?,?,?,?)",
            ('person', new_canonical, display, raw_names, 0, 'medium', note))
        new_id = int(cur.lastrowid)
        for ri in clusters[ci]:
            r = recs[ri]
            tbl = r.table
            store.conn.execute(
                f"UPDATE {tbl} SET entity_id=? WHERE id=?", (new_id, r.rowid))
    return len(clusters) - 1


def main() -> None:
    store = Store("rpscope.db")
    client = LLMClient()
    print(f"LLM enabled={client.enabled}")

    # 找记录数>20 的 person 实体(高合并候选)
    merged = list(store.conn.execute(
        "SELECT * FROM ("
        "  SELECT e.entity_id, e.canonical_name, e.display_name, "
        "    (SELECT COUNT(*) FROM position p WHERE p.entity_id=e.entity_id) + "
        "    (SELECT COUNT(*) FROM holding h WHERE h.entity_id=e.entity_id) AS n "
        "  FROM entity e WHERE e.entity_type='person' AND e.is_channel=0"
        ") WHERE n > 20 ORDER BY n DESC LIMIT 5"))
    print(f"高合并 person 实体: {len(merged)} 个 (记录数>20)", flush=True)

    total_split = 0
    for idx, r in enumerate(merged):
        n_before = r[3]
        print(f"[{idx+1}/{len(merged)}] E:{r[0]} {r[2]} 记录{n_before} 拆分中...", flush=True)
        k = split_entity(store, r[0], r[1], r[2], client)
        store.commit()  # 每人提交, 防中断丢进度
        if k:
            total_split += k
            print(f"  -> 拆出{k}新簇", flush=True)
        else:
            print(f"  -> 无拆分", flush=True)
    print(f"共拆出 {total_split} 个新 person 实体", flush=True)

    # 重建图
    G = build_graph(store)
    save_graph(G)
    n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
    n_ent = G.number_of_nodes() - n_co
    distinct_deg = {n: len(set(G.successors(n)) | set(G.predecessors(n))) for n in G}
    top = sorted(distinct_deg.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"重建图: 公司{n_co} 实体{n_ent} 边{G.number_of_edges()}")
    print("Top5 度:")
    for n, d in top:
        nd = G.nodes[n]
        print(f"  {d} {nd.get('kind')} {nd.get('etype','')} {nd.get('name') or nd.get('code') or n}")
    print(f"max degree = {top[0][1] if top else 0}")
    store.close()


if __name__ == "__main__":
    main()
