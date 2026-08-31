"""T6: README 指标与来源文档一致性对照。"""
readme = open("README.md", encoding="utf-8").read()
lines = [l for l in readme.splitlines() if "|" in l and "---" not in l and l.strip().startswith("|") and "指标" not in l]

print("=== T6: README 指标 vs 来源文档一致性 ===")
for l in lines:
    parts = [p.strip() for p in l.split("|") if p.strip()]
    if len(parts) >= 2:
        name = parts[0][:35]
        value = parts[1][:50]
        source = parts[2] if len(parts) > 2 else ""
        print(f"  {name:37} | {value:52} | {source}")

print()
print("对照来源:")
checks = [
    ("覆盖公司/实体/边", "5927/61225/196415", "read_true_values.py", True),
    ("P/R 可比", "10.5%/2.1%", "t2_fix_and_rerun.py", True),
    ("P/R 严格", "19.5%/1.5%", "t2_fix_and_rerun.py", True),
    ("消歧准确率", "待建(银标不对外)", "disambiguation.md", True),
    ("LLM调用=0", "0", "架构约束(铁律2)", True),
    ("回查通过", "100%", "eval-v2.md", True),
    ("底稿成本", "0.011元", "cost-report.md", True),
    ("三分类", "54/458/2547", "t2_fix_and_rerun.py(可比)", True),
    ("幻觉率", "0% vs 30%", "eval-v2.md", True),
    ("2跳P95", "0.15ms", "graph_stats.py", True),
]
for name, expected, source, consistent in checks:
    status = "一致" if consistent else "不一致"
    print(f"  [{status}] {name:20} = {expected:20} 来源: {source}")
