"""从 SQLite 事实源重建 networkx 图。幂等: 每次从 PG/SQLite 全量重建, 结果覆盖 .cache/graph.pkl。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.graph.store import build_graph, save_graph
from src.store.db import Store


def main() -> None:
    store = Store("rpscope.db")
    print("rebuilding graph from SQLite ...")
    G = build_graph(store)
    save_graph(G)
    n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
    n_ent = G.number_of_nodes() - n_co
    e_holds = sum(1 for *_, d in G.edges(data=True) if d.get("kind") == "HOLDS")
    e_serves = sum(1 for *_, d in G.edges(data=True) if d.get("kind") == "SERVES_AS")
    e_ctrl = sum(1 for *_, d in G.edges(data=True) if d.get("kind") == "CONTROLS")
    print(f"  公司节点: {n_co} | 实体节点(非通道): {n_ent}")
    print(f"  HOLDS: {e_holds} | SERVES_AS: {e_serves} | CONTROLS: {e_ctrl}")
    print(f"  总边数: {G.number_of_edges()} -> .cache/graph.pkl")
    store.close()


if __name__ == "__main__":
    main()
