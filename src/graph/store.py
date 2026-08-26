"""RPScope 图计算视图 - networkx 实现 (P1 临时; Neo4j 就绪后换 Cypher, 接口不变)。

原则: 图是从事实源(SQLite)完全重建的计算视图, 通道实体(is_channel=1)不导入。
节点: C:{stock_code} 公司 / E:{entity_id} 实体(person/org/fund)
边: HOLDS(entity->company) / SERVES_AS(person->company) / CONTROLS(entity->company)
所有边带 valid_from / source。
"""
from __future__ import annotations

import pickle
from pathlib import Path

import networkx as nx

from src.store.db import Store

GRAPH_PATH = Path(".cache/graph.pkl")


def build_graph(store: Store) -> nx.MultiDiGraph:
    G: nx.MultiDiGraph = nx.MultiDiGraph()

    # 公司节点
    for r in store.conn.execute("SELECT stock_code, short_name FROM company"):
        G.add_node(f"C:{r['stock_code']}", kind="company", code=r["stock_code"], name=r["short_name"])

    # 非通道实体节点 (通道实体不入图)
    for r in store.conn.execute(
        "SELECT entity_id, entity_type, display_name FROM entity WHERE is_channel=0"
    ):
        G.add_node(f"E:{r['entity_id']}", kind="entity", eid=r["entity_id"],
                   etype=r["entity_type"], name=r["display_name"])

    non_channel_eids = {n for n in G if n.startswith("E:")}

    # 持股边
    for r in store.conn.execute(
        "SELECT entity_id, stock_code, report_period, ratio, valid_from, source FROM holding"
    ):
        u = f"E:{r['entity_id']}"
        if u in non_channel_eids:
            G.add_edge(u, f"C:{r['stock_code']}", kind="HOLDS",
                       report_period=r["report_period"], ratio=r["ratio"],
                       valid_from=r["valid_from"], source=r["source"])

    # 任职边
    for r in store.conn.execute(
        "SELECT entity_id, stock_code, title, title_class, valid_from, source FROM position"
    ):
        u = f"E:{r['entity_id']}"
        if u in non_channel_eids:
            G.add_edge(u, f"C:{r['stock_code']}", kind="SERVES_AS",
                       title=r["title"], title_class=r["title_class"],
                       valid_from=r["valid_from"] or "", source=r["source"])

    # 实控人边
    for r in store.conn.execute(
        "SELECT stock_code, entity_id, control_ratio, valid_from, source FROM actual_controller"
    ):
        u = f"E:{r['entity_id']}"
        if u in non_channel_eids:
            G.add_edge(u, f"C:{r['stock_code']}", kind="CONTROLS",
                       control_ratio=r["control_ratio"],
                       valid_from=r["valid_from"] or "", source=r["source"])

    return G


def save_graph(G: nx.MultiDiGraph, path: Path = GRAPH_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_graph(path: Path = GRAPH_PATH) -> nx.MultiDiGraph:
    with open(path, "rb") as f:
        return pickle.load(f)


def neighbors_2hop(G: nx.MultiDiGraph, stock_code: str) -> set[str]:
    """公司 -> 持有/控制/任职实体 -> 其他公司 (2 跳, 不限边类型)。"""
    start = f"C:{stock_code}"
    if start not in G:
        return set()
    seen: set[str] = set()
    for ent in G.predecessors(start):  # 公司 <- 实体
        for other in G.successors(ent):  # 实体 -> 公司
            if other != start and other.startswith("C:"):
                seen.add(other)
    return seen
