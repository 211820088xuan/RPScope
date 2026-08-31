"""运行验证 - 全部端点。"""
import sys
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from src.serve.main import app

c = TestClient(app)

# 1. 首页
r = c.get("/")
print(f"1. 首页: {r.status_code}, HTML={len(r.text)}字符")

# 2. 公司
r = c.get("/api/company/300750")
d = r.json()
print(f"2. 公司: {d['stock_code']} {d['short_name']}")

# 3. 底稿
r = c.get("/api/report/002594")
d = r.json()
print(f"3. 底稿: matched={d['related']['n_matched']} sys={d['related']['n_system_only']} gold={d['related']['n_gold_only']} events={len(d['events'])}")

# 4. 问答
r = c.post("/api/ask", json={"question": "002594的前十大股东"})
a = r.json()
print(f"4. 问答: intent={a['intent']} LLM={a['used_llm']} verify={a['verify']['passed']} {a['elapsed_ms']:.0f}ms")
print(f"   答案: {a['answer'][:100]}")

# 5. PDF
r = c.get("/api/report/002594/pdf")
print(f"5. PDF: {r.status_code} {len(r.content)}字节")

# 6. 随机
r = c.get("/api/random")
d = r.json()
print(f"6. 随机: {d['stock_code']} {d['short_name']}")

# 7. 统计
r = c.get("/api/stats")
d = r.json()
print(f"7. 统计: cache={d['cache']}")
