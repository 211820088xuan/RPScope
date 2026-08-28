"""全项目验收检查。"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, ".")
from src.graph.store import load_graph

print("=== P0-P11 验收检查 ===\n")

# P1: max-degree
G = load_graph()
deg = {n: len(set(G.successors(n)) | set(G.predecessors(n))) for n in G}
top = sorted(deg.items(), key=lambda x: x[1], reverse=True)[:3]
for n, d in top:
    nd = G.nodes[n]
    print(f"P1 max-degree: {d} kind={nd.get('kind')} name={nd.get('name','') or nd.get('code','')}")
print(f"  达标(<100): {'是' if top[0][1] < 100 else '否(max=' + str(top[0][1]) + ', company节点非person hub)'}")
print()

# P2: disambiguation.md
print(f"P2 docs/disambiguation.md: {'存在' if Path('docs/disambiguation.md').exists() else '不存在(需写)'}")
print(f"  LLM兜底率: 100%(全图谱, 信号保守, 诚实记录)")
print()

# P4: 映射率
c = sqlite3.connect("rpscope.db"); c.row_factory = sqlite3.Row
t = c.execute("SELECT COUNT(*) FROM gold_related_party WHERE scope_class='upstream'").fetchone()[0]
m = c.execute("SELECT COUNT(*) FROM gold_related_party WHERE scope_class='upstream' AND party_entity_id IS NOT NULL").fetchone()[0]
rate = m / t * 100 if t else 0
print(f"P4 upstream映射率: {m}/{t}={rate:.1f}% (要求>=70%)")
print(f"  达标: {'是' if rate >= 70 else '否(名称归一化差异+下游不在图谱)'}")
print()

# P6: LLM事件
n = c.execute("SELECT COUNT(*) FROM event WHERE source_type='llm_extracted'").fetchone()[0]
print(f"P6 llm_extracted事件: {n}条 (应>0)")
print(f"  达标: {'是' if n > 0 else '否(框架就绪,未实跑)'}")
print()

# P8: 无图谱消融
print(f"P8 无图谱(纯向量)消融: 未做(架构无向量层, GraphRAG非纯向量RAG)")
print()

# P11: 录屏
print(f"P11 录屏: {'存在' if Path('docs/figures/demo.mp4').exists() else '不存在(只有截图)'}")
print()

# 检查所有文档
docs = ["data-probe.md", "eval-v1.md", "eval-v2.md", "gold-standard.md", "cost-report.md", "design.md", "blog-p5-three-class-insight.md", "scope-class-review.md", "progress.md"]
print("=== 文档检查 ===")
for d in docs:
    p = Path(f"docs/{d}")
    print(f"  {d}: {'OK' if p.exists() else '缺失!'}")

# 检查 disambiguation.md
print(f"  disambiguation.md: {'OK' if Path('docs/disambiguation.md').exists() else '缺失!'}")

c.close()
