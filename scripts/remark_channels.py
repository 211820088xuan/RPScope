"""重新评估所有实体的 is_channel 标记(基于 raw_names 全部写法)。
修复 P1 bug: ggcg/positions/controllers ingest 路径未调用 is_channel_name,
导致同实体的不同创建路径下 is_channel=0。本脚本统一回填, 然后重建图。"""
import re
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import yaml
from src.normalize.name import is_channel_name, normalize_name
from src.store.db import Store
from src.graph.store import build_graph, save_graph


def main() -> None:
    store = Store("rpscope.db")
    ce = yaml.safe_load(Path("config/rules.yaml").read_text(encoding="utf-8"))["channel_exclusion"]
    exact = set(ce.get("exact", []))
    pats = [re.compile(p) for p in ce.get("patterns", [])]

    rows = list(store.conn.execute(
        "SELECT entity_id, display_name, raw_names FROM entity"))
    flagged = 0
    for r in rows:
        raws = json.loads(r["raw_names"] or "[]") if r["raw_names"] else []
        names = [r["display_name"] or ""] + raws
        ch = any(is_channel_name(str(n), exact, pats) for n in names if n)
        if ch:
            store.conn.execute("UPDATE entity SET is_channel=1 WHERE entity_id=?", (r["entity_id"],))
            flagged += 1
    store.commit()
    total = len(rows)
    print(f"实体总数 {total} | 标记为通道 {flagged}")

    # 重建图
    G = build_graph(store)
    save_graph(G)
    n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
    n_ent = G.number_of_nodes() - n_co
    print(f"重建图: 公司 {n_co} | 非通道实体 {n_ent} | 边 {G.number_of_edges()}")


if __name__ == "__main__":
    main()
