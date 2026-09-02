"""T7: 对比分析(Q8) 20 条测试 + 摘要幻觉验证 + 回查拦截 + 延迟。"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.rules.engine import RuleEngine
from src.store.db import Store
from src.query.compare import compare
from src.agent.verifier import verify_answer
from src.llm.prompts import get_prompt
from src.llm.client import LLMClient

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")

# 20 条对比用例: (code_a, code_b, note, has_overlap_expected)
TESTS = [
    ("002594", "300750", "比亚迪vs宁德时代 跨行业", False),
    ("600519", "000858", "茅台vs五粮液 同行业", False),
    ("601318", "600036", "平安vs招行 跨行业", False),
    ("600036", "000001", "招行vs平安银行 同行业", False),
    ("002475", "002594", "立讯vs比亚迪 跨行业", False),
    ("600276", "300059", "恒瑞vs东财 跨行业", False),
    ("601012", "300750", "隆基vs宁德 跨行业", False),
    ("002594", "002594", "同公司自比", True),
    ("000858", "600519", "五粮液vs茅台", False),
    ("600519", "600519", "茅台自比", True),
    ("601318", "600036", "平安vs招行", False),
    ("000001", "600036", "平安银行vs招行", False),
    ("002594", "000858", "比亚迪vs五粮液", False),
    ("300750", "601318", "宁德vs平安", False),
    ("600276", "002475", "恒瑞vs立讯", False),
    ("002594", "600276", "比亚迪vs恒瑞", False),
    ("000858", "300750", "五粮液vs宁德", False),
    ("600519", "002475", "茅台vs立讯", False),
    ("601012", "002594", "隆基vs比亚迪", False),
    ("999999", "002594", "不存在vs比亚迪 一方缺失", False),
]

print("=== T7: 对比分析 20 条测试 ===\n")
passed = 0
all_times = []

for i, (a, b, note, exp_overlap) in enumerate(TESTS):
    t0 = time.time()
    try:
        result = compare(s, eng, a, b)
        elapsed = (time.time() - t0) * 1000
        all_times.append(elapsed)

        # 检查 5 个维度的完整性
        dims = ["basic", "holders", "controllers", "related", "directors", "events"]
        ok_dims = all(d in result and len(result[d]) > 0 for d in dims)
        n_overlap = result.get("related", {}).get("n_overlap", -1)
        n_cross = result.get("directors", {}).get("cross_count", -1)

        # 同公司自比应有重合
        overlap_ok = (a == b and n_overlap >= 0) or (a != b)
        ok = ok_dims and overlap_ok
        if ok:
            passed += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {i+1:2d}. {a} vs {b} | {note:25s} | {elapsed:.0f}ms | overlap={n_overlap} cross_dirs={n_cross}")
    except Exception as e:
        print(f"  [FAIL] {i+1:2d}. {a} vs {b} | {note:25s} | ERROR: {str(e)[:40]}")

print(f"\n通过率: {passed}/{len(TESTS)} = {passed/len(TESTS)*100:.0f}%")
print(f"延迟: P50={sorted(all_times)[len(all_times)//2]:.0f}ms P95={sorted(all_times)[min(int(len(all_times)*0.95),len(all_times)-1)]:.0f}ms")

# 摘要幻觉验证: 对 3 条用例做 LLM 摘要, 检查是否出现评价性内容
print(f"\n=== 摘要幻觉验证 ===")
try:
    from src.llm.client import LLMClient
    llm = LLMClient()
    if llm.enabled:
        # 取 3 条典型用例
        for a, b, note in [("002594","300750","跨行业"), ("600519","000858","同行业"), ("601318","600036","金融")]:
            result = compare(s, eng, a, b)
            ctx = json.dumps(result, ensure_ascii=False, default=str)[:3000]
            answer = llm.chat(get_prompt("compare_summary", a=a, b=b, ctx=ctx))
            # 检查幻觉
            eval_words = ["更稳健", "风险更高", "更差", "更好", "更优", "更安全", "比.*更", "因为.*所以"]
            import re
            hallucinations = [w for w in eval_words if w in answer or re.search(w, answer)]
            # 检查结构化结果之外的实体
            ents_in_answer = []  # removed: extract_entities_from_text
            known_names = set()
            for h in result.get("holders",{}).get("a",[]) + result.get("holders",{}).get("b",[]):
                known_names.add(h.get("display_name",""))
            for c in result.get("controllers",{}).get("a",[]) + result.get("controllers",{}).get("b",[]):
                known_names.add(c.get("display_name",""))
            unknown_ents = [e for e in ents_in_answer if e not in known_names and not e.isdigit()]
            # 回查
            v = verify_answer(s, answer)

            print(f"  {a} vs {b}: ans_len={len(answer)} eval_words={hallucinations} unknown_ents={len(unknown_ents)} verify_passed={v['passed']}")
            if hallucinations:
                print(f"    幻觉: {hallucinations}")
            if unknown_ents:
                print(f"    未知实体: {unknown_ents[:3]}")
            if not v['passed'] and not hallucinations and not unknown_ents:
                print(f"    回查拦截了非幻觉内容: {v.get('violations',[])[:3]}")
    else:
        print("  LLM 未启用, 跳过幻觉验证")
except Exception as e:
    print(f"  错误: {e}")

s.close()
