"""P1: 检查福石控股168度的构成(person vs org vs company)。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.graph.store import load_graph

G = load_graph()
fushi = None
for n, d in G.nodes(data=True):
    if d.get("name") == "福石控股":
        fushi = n; break

if fushi:
    neighbors = set(G.predecessors(fushi)) | set(G.successors(fushi))
    by_kind = {}
    for n in neighbors:
        nd = G.nodes[n]
        k = nd.get("etype") or nd.get("kind") or "?"
        by_kind[k] = by_kind.get(k, 0) + 1
    print(f"福石控股 总邻居: {len(neighbors)}")
    for k, v in sorted(by_kind.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    # person邻居按度排序
    persons = [n for n in neighbors if G.nodes[n].get("etype") == "person"]
    print(f"\nperson邻居: {len(persons)}")
    for p in sorted(persons, key=lambda x: G.degree(x), reverse=True)[:5]:
        print(f"  {G.nodes[p].get('name','')} degree={G.degree(p)}")
    
    # org邻居
    orgs = [n for n in neighbors if G.nodes[n].get("etype") == "org"]
    print(f"\norg邻居: {len(orgs)}")
    for o in sorted(orgs, key=lambda x: G.degree(x), reverse=True)[:5]:
        print(f"  {G.nodes[o].get('name','')} degree={G.degree(o)}")
else:
    print("福石控股 not found")
