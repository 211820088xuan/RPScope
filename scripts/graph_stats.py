"""图统计: 节点/边数、度分布、最高度数 Top20、2 跳查询耗时。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.graph.store import load_graph, neighbors_2hop


def main() -> None:
    G = load_graph()
    n_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
    n_ent = G.number_of_nodes() - n_co
    print(f"节点: 公司 {n_co} | 实体(非通道) {n_ent} | 总 {G.number_of_nodes()}")
    print(f"边: {G.number_of_edges()}")

    # 度=不同邻居数(MultiDiGraph.degree 会把 ggcg 多期变动产生的平行边重复计数,
    # 故用 successors/predecessors 去重后的不同邻居数)
    distinct_deg = {}
    for n in G:
        nb = set(G.successors(n)) | set(G.predecessors(n))
        distinct_deg[n] = len(nb)
    top = sorted(distinct_deg.items(), key=lambda x: x[1], reverse=True)[:20]
    print("\n最高不同邻居数 Top20:")
    for n, d in top:
        nd = G.nodes[n]
        name = nd.get("name") or nd.get("code") or n
        kind = nd.get("kind") or ("entity" if n.startswith("E:") else "company")
        etype = nd.get("etype", "")
        print(f"  {d:>5}  {kind:<7} {etype:<8} {name}")

    max_deg = top[0][1] if top else 0
    print(f"\n排除通道后最高不同邻居数 = {max_deg} "
          + ("[OK] <100" if max_deg < 100 else "[WARN] >=100, 排除名单需补全"))

    # 2 跳查询耗时 (取 5 家公司)
    companies = [n.split(":", 1)[1] for n, d in G.nodes(data=True) if d.get("kind") == "company"][:5]
    print(f"\n2跳邻居查询 ({len(companies)} 家样本):")
    for code in companies:
        t0 = time.perf_counter()
        nb = neighbors_2hop(G, code)
        dt = (time.perf_counter() - t0) * 1000
        print(f"  {code}: {len(nb)} 个 2 跳邻居, {dt:.2f}ms")
    # P95 代理: 取 50 家
    more = [n.split(":", 1)[1] for n, d in G.nodes(data=True) if d.get("kind") == "company"][:50]
    times = []
    for code in more:
        t0 = time.perf_counter()
        neighbors_2hop(G, code)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p95 = times[int(len(times) * 0.95)] if times else 0
    print(f"  50 样本 2 跳 P95 = {p95:.2f}ms "
          + ("[OK] <500ms" if p95 < 500 else "[WARN] >=500ms"))


if __name__ == "__main__":
    main()
