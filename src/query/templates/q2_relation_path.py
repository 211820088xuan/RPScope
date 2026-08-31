"""Q2: 查两个实体间的关系路径。"""
from __future__ import annotations
from src.rules.engine import RuleEngine
from src.rules.path import render_path
from src.store.db import Store


def execute(store: Store, engine: RuleEngine, slots: dict) -> dict:
    ea = slots["entity_a"]
    eb = slots["entity_b"]
    max_hops = slots.get("max_hops", 3)
    # 如果 A 是公司, 查 B 是否在 A 的关联方候选里
    if ea.get("type") == "company":
        cands = engine.evaluate(store, ea["code"])
        target = eb.get("code") and f"C:{eb['code']}" or eb.get("name", "")
        hits = [c for c in cands if target in (c.party_id, c.party_name)
                or eb.get("name") and eb["name"] in c.party_name]
        if hits:
            return {"template": "Q2", "related": True,
                    "rule": hits[0].rule_id, "confidence": hits[0].confidence,
                    "path": render_path(hits[0].path),
                    "evidence_source": "rules_engine"}
    # 双向检查
    if eb.get("type") == "company":
        cands = engine.evaluate(store, eb["code"])
        target = ea.get("code") and f"C:{ea['code']}" or ea.get("name", "")
        hits = [c for c in cands if target in (c.party_id, c.party_name)
                or ea.get("name") and ea["name"] in c.party_name]
        if hits:
            return {"template": "Q2", "related": True,
                    "rule": hits[0].rule_id, "confidence": hits[0].confidence,
                    "path": render_path(hits[0].path),
                    "evidence_source": "rules_engine"}
    # 图遍历 fallback
    from src.graph.store import load_graph
    G = load_graph()
    try:
        import networkx as nx
        na = ea.get("code") and f"C:{ea['code']}" or ea.get("name")
        nb = eb.get("code") and f"C:{eb['code']}" or eb.get("name")
        path = nx.shortest_path(G, na, nb) if G.has_node(na) and G.has_node(nb) else None
    except Exception:
        path = None
    return {"template": "Q2", "related": path is not None, "path": " -> ".join(path) if path else "",
            "evidence_source": "graph_traversal"}
