"""P2 银标评测 - 用独立模型 qwen-max 当裁判(与消歧 LLM glm-5.2 不同家族)。

对 90 对同名候选:
  系统: resolve_pair(规则 + glm-5.2 兜底) -> pred
  裁判: qwen-max 独立判断 -> silver_gold
  比较: pred == silver_gold
诚实披露: 银标=独立模型裁判, 非人工金标准。
增量写结果到 data/annotations/silver_eval.jsonl, 防中断丢进度。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.disambiguate.resolver import resolve_pair
from src.disambiguate.signals import Record, Stats
from src.llm.client import LLMClient
from src.store.db import Store

ANN = Path("data/annotations/person_disambig.jsonl")
OUT = Path("data/annotations/silver_eval.jsonl")
JUDGE_MODEL = "qwen3.7-max"


def judge(client: LLMClient, name: str, ra: Record, rb: Record) -> tuple[bool, str]:
    prompt = (
        "你是实体消歧的独立裁判。判断两条 A 股董监高/持股变动记录是否为同一自然人。\n"
        "中国人名重名率极高。依据公司、行业、时段、职务综合判断。信息不足时倾向'不同人'。\n\n"
        f"姓名: {name}\n"
        f"记录A: 公司{ra.stock_code}, 职务={ra.title}, 日期={ra.valid_from}, 来源={ra.source}\n"
        f"记录B: 公司{rb.stock_code}, 职务={rb.title}, 日期={rb.valid_from}, 来源={rb.source}\n\n"
        '输出 JSON: {"same_person": true/false, "reason": "..."}'
    )
    try:
        obj = client.chat_json([{"role": "user", "content": prompt}],
                               schema_keys=["same_person", "reason"])
        return bool(obj.get("same_person", False)), str(obj.get("reason", ""))
    except Exception as e:
        return False, f"judge降级: {type(e).__name__}: {e}"


def main() -> None:
    pairs = [json.loads(l) for l in ANN.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"标注集 {len(pairs)} 对 | 系统LLM=glm-5.2 | 裁判={JUDGE_MODEL}", flush=True)

    sys_client = LLMClient()                     # glm-5.2, 消歧兜底
    judge_client = LLMClient(model=JUDGE_MODEL)   # qwen-max, 独立裁判
    print(f"系统LLM enabled={sys_client.enabled} | 裁判enabled={judge_client.enabled}", flush=True)
    if not judge_client.enabled:
        print("裁判不可用, 退出"); return

    store = Store("rpscope.db")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 续跑: 已处理的 name+rec_a 跳过
    done = set()
    if OUT.exists():
        for l in OUT.read_text(encoding="utf-8").splitlines():
            if l.strip():
                o = json.loads(l); done.add((o["name"], str(o["rec_a"])))

    tp = fp = tn = fn = 0
    by_conf: dict[str, list] = {}
    llm_used = 0
    n = 0
    for i, p in enumerate(pairs):
        key = (p["name"], str(p["rec_a"]))
        if key in done:
            continue
        ra = Record(**{k: p["rec_a"].get(k, "") for k in ("stock_code", "title", "valid_from", "source")})
        rb = Record(**{k: p["rec_b"].get(k, "") for k in ("stock_code", "title", "valid_from", "source")})
        # 该 name 的全局统计
        n_co = 0
        row = store.conn.execute(
            "SELECT entity_id FROM entity WHERE entity_type='person' AND canonical_name=?",
            (p.get("canonical") or p["name"],)).fetchone()
        if row:
            n_co = store.conn.execute(
                "SELECT COUNT(DISTINCT stock_code) FROM ("
                "  SELECT stock_code FROM position WHERE entity_id=? UNION SELECT stock_code FROM holding WHERE entity_id=?)",
                (row[0], row[0])).fetchone()[0]
        stats = Stats(name_freq=0, name_company_count=n_co)

        v = resolve_pair(p["name"], ra, rb, stats, sys_client)  # 系统: 规则+glm-5.2
        same_gold, reason = judge(judge_client, p["name"], ra, rb)  # 裁判: qwen-max
        pred = v.same_person
        if v.used_llm:
            llm_used += 1

        correct = (pred == same_gold)
        if same_gold and pred: tp += 1
        elif (not same_gold) and pred: fp += 1
        elif (not same_gold) and (not pred): tn += 1
        else: fn += 1
        by_conf.setdefault(v.confidence, []).append(int(correct))
        n += 1

        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "name": p["name"], "rec_a": p["rec_a"], "rec_b": p["rec_b"],
                "rule_score": v.score, "sys_pred": pred, "sys_conf": v.confidence, "used_llm": v.used_llm,
                "silver_gold": same_gold, "judge_reason": reason, "correct": correct,
            }, ensure_ascii=False) + "\n")
        if n % 10 == 0:
            print(f"  [{n}/{len(pairs)}] acc={(tp+tn)/n*100:.1f}% llm={llm_used}", flush=True)

    acc = (tp + tn) / n if n else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    print(f"\n=== 银标评测结果 (n={n}, 裁判={JUDGE_MODEL}, 非人工金标准) ===", flush=True)
    print(f"准确率 {acc*100:.1f}% | precision {prec*100:.1f}% | recall {rec*100:.1f}%")
    print(f"混淆矩阵: TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"LLM 兜底触发: {llm_used}/{n} ({llm_used/n*100 if n else 0:.1f}%)")
    for conf, hits in sorted(by_conf.items()):
        print(f"  {conf} 档准确率 {sum(hits)/len(hits)*100:.1f}% (n={len(hits)})")
    print(f"注: 银标=独立模型({JUDGE_MODEL})裁判, 与消歧LLM(glm-5.2)不同家族; 非人工金标准。")


if __name__ == "__main__":
    main()
