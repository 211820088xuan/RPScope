"""验证 T8 过滤 + Q8 分类。"""
import sys
sys.path.insert(0, ".")
from src.query.dict_match import CompanyMatcher
from src.query.intent import classify
import sqlite3

conn = sqlite3.connect("rpscope.db")
conn.row_factory = sqlite3.Row
cm = CompanyMatcher(conn)
print("词典:", cm._stats)

c1 = classify("比亚迪和宁德时代对比一下")
print(f"Q8: {c1}")
c2 = classify("比亚迪和宁德时代关联方重合")
print(f"Q6: {c2}")

# 对比测试
from src.rules.engine import RuleEngine
from src.store.db import Store
from src.query.compare import compare

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")
result = compare(s, eng, "002594", "300750")
print(f"\n对比 002594 vs 300750:")
print(f"  关联方: A={result['related']['n_a']} B={result['related']['n_b']} 重合={result['related']['n_overlap']}")
print(f"  董监高: A={result['directors']['n_a']} B={result['directors']['n_b']} 交叉={result['directors']['cross_count']}")
print(f"  事件: A={result['events']['n_a']} B={result['events']['n_b']}")
print(f"  实控人: A={[c['display_name'] for c in result['controllers']['a']]}")
print(f"         B={[c['display_name'] for c in result['controllers']['b']]}")
s.close()
conn.close()
