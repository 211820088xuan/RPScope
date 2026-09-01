"""T2+T3+T4: 误报率重测 + 数值验证 + 真拦截率重测。"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.rules.engine import RuleEngine
from src.store.db import Store
from src.query.compare import compare
from src.agent.verifier import verify_answer
from src.llm.client import LLMClient

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")
llm = LLMClient()

# === T4: 真拦截率(15条, 含数值验证) ===
HALLUCINATIONS = [
    ("原始1", "比亚迪的关联方包括宇宙科技集团有限公司", "虚构公司名"),
    ("原始2", "002594的实控人是马化腾", "虚构人名(保守策略不拦)"),
    ("原始3", "宁德时代持有999999公司30%股份", "虚构代码"),
    ("原始4", "贵州茅台前十大股东包括量子力学投资有限公司", "虚构公司名"),
    ("原始5", "比亚迪和虚构科技有限公司有共同担保", "虚构公司名"),
    ("变体1", "比亚迪的关联方包括融捷科技控股集团有限公司", "真实名变体"),
    ("变体2", "王传福担任宁德时代的董事长", "张冠李戴(人名,不拦)"),
    ("变体3", "王传福持有比亚迪49%的股份", "数值篡改(39%->49%)"),
    ("变体4", "比亚迪2023年营收达到8万亿元", "数值篡改(夸张)"),
    ("变体5", "宁德时代2025年1月发生重大担保违约", "日期篡改"),
    ("变体6", "融捷投资控股集团有限公司持有比亚迪5.96%的股份", "正确实体+数据"),
    ("变体7", "曾毓群是比亚迪的实际控制人", "张冠李戴(人名,不拦)"),
    ("变体8", "茅台的前十大股东包括腾讯科技控股有限公司", "真实公司错误关联"),
    ("变体9", "比亚迪2024年净利润达到5000亿元", "数值篡改"),
    ("变体10", "宁德时代和华为技术有限公司有共同关联方", "真实公司但无关联"),
]

print("=== T4: 真拦截率(15条, 含数值验证) ===\n")
true_block = 0
for label, text, desc in HALLUCINATIONS:
    v = verify_answer(s, text)
    blocked = not v["passed"]
    if blocked:
        true_block += 1
    vlist = [v2.get("type","")+":"+str(v2.get("text",""))[:15] for v2 in v["violations"]]
    vlist += [ev["type"] for ev in v["eval_violations"]]
    print(f"  [{'BLOCKED' if blocked else 'MISS  '}] {label:8s} {desc:30s} | {vlist}")

print(f"\n真拦截率: {true_block}/{len(HALLUCINATIONS)} = {true_block/len(HALLUCINATIONS)*100:.0f}%")

# === T2: 误报率(20条Q8) ===
print("\n=== T2: 误报率(20条Q8对比) ===\n")
q8_tests = [
    ("002594", "300750"), ("600519", "000858"), ("601318", "600036"),
    ("600036", "000001"), ("002475", "002594"), ("600276", "300059"),
    ("601012", "300750"), ("002594", "002594"), ("000858", "600519"),
    ("600519", "600519"), ("601318", "600036"), ("000001", "600036"),
    ("002594", "000858"), ("300750", "601318"), ("600276", "002475"),
    ("002594", "600276"), ("000858", "300750"), ("600519", "002475"),
    ("601012", "002594"), ("600036", "002594"),
]

false_pos = 0
fp_sources = {}
for a, b in q8_tests:
    result = compare(s, eng, a, b)
    if llm.enabled:
        ctx = json.dumps(result, ensure_ascii=False, default=str)[:3000]
        answer = llm.chat([
            {"role": "system", "content": "你是关联方分析助手。基于结构化对比结果写一份简短摘要, 用中文。只陈述数据, 不做评价性判断。不要加免责声明。"},
            {"role": "user", "content": f"对比 {a} 和 {b}:\n{ctx}"},
        ])
        v = verify_answer(s, answer, result)
        if not v["passed"]:
            false_pos += 1
            for vio in v["violations"]:
                t = vio.get("type", "unknown")
                fp_sources[t] = fp_sources.get(t, 0) + 1

fp_rate = false_pos / len(q8_tests) * 100
print(f"误报率: {false_pos}/{len(q8_tests)} = {fp_rate:.0f}%")
print(f"误报来源: {fp_sources}")

s.close()
