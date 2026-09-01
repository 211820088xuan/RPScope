"""T3: 10条差异悬殊对比 + 摘要幻觉对抗测试。"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.rules.engine import RuleEngine
from src.store.db import Store
from src.query.compare import compare
from src.agent.verifier import verify_answer, check_evaluative
from src.llm.client import LLMClient

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")
llm = LLMClient()

# 10条差异悬殊: (a, b, note)
TESTS = [
    ("002594", "300750", "比亚迪vs宁德 跨行业龙头"),
    ("600519", "000858", "茅台vs五粮液 同行业竞品"),
    ("601318", "600036", "平安vs招行 金融双雄"),
    ("002594", "600276", "比亚迪vs恒瑞 制造vs医药"),
    ("600519", "002475", "茅台vs立讯 消费vs电子"),
    ("300750", "601012", "宁德vs隆基 电池vs光伏"),
    ("002594", "600036", "比亚迪vs招行 实业vs金融"),
    ("000858", "600519", "五粮液vs茅台 白酒双雄"),
    ("601318", "000001", "平安vs平安银行 集团vs子公司"),
    ("600036", "002594", "招行vs比亚迪 金融vs制造"),
]

print("=== T3: 10条差异悬殊对比 + 摘要幻觉对抗 ===\n")
eval_count = 0
verify_block_count = 0
times = []

for a, b, note in TESTS:
    t0 = time.time()
    result = compare(s, eng, a, b)
    elapsed = (time.time() - t0) * 1000
    times.append(elapsed)

    if llm.enabled:
        ctx = json.dumps(result, ensure_ascii=False, default=str)[:3000]
        answer = llm.chat([
            {"role": "system", "content": "你是关联方分析助手。基于结构化对比结果写一份简短摘要, 用中文。只陈述数据, 不做评价性判断(如更好/更差/更稳健/风险更高)。不要加免责声明。"},
            {"role": "user", "content": f"对比 {a} 和 {b}:\n{ctx}"},
        ])
        # 检查幻觉
        eval_violations = check_evaluative(answer)
        v = verify_answer(s, answer)
        has_eval = len(eval_violations) > 0
        has_verify_block = not v["passed"]
        if has_eval:
            eval_count += 1
        if has_verify_block:
            verify_block_count += 1
        n_overlap = result["related"]["n_overlap"]
        n_cross = result["directors"]["cross_count"]
        print(f"  {a} vs {b} | {note:25s} | {elapsed:.0f}ms overlap={n_overlap} eval={'YES' if has_eval else 'no'} verify_block={'YES' if has_verify_block else 'no'} ans_len={len(answer)}")
        if has_eval:
            print(f"    评价性内容: {[v['type']+':'+v['text'][:20] for v in eval_violations]}")
    else:
        n_overlap = result["related"]["n_overlap"]
        print(f"  {a} vs {b} | {note:25s} | {elapsed:.0f}ms overlap={n_overlap} (LLM disabled)")

print(f"\n=== 汇总 ===")
print(f"对比延迟: P50={sorted(times)[len(times)//2]:.0f}ms P95={sorted(times)[min(int(len(times)*0.95),len(times)-1)]:.0f}ms")
print(f"评价性表述出现: {eval_count}/10")
print(f"回查拦截: {verify_block_count}/10")
print(f"未被拦截的评价性: {eval_count - verify_block_count if eval_count > verify_block_count else 0}")

s.close()
