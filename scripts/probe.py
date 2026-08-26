"""RPScope P0 数据探针 - 验证 akshare 全部接口可用性。

铁律 1 对应：P0 数据探针必须诚实记录结果。每个接口记录：
是否可调用 / 参数签名 / 返回列名 / 行数 / 耗时 / 异常信息。
所有调用走 AkshareClient（缓存+限流+重试），探针结果必须真实，禁止 mock。

增量写入 .cache/probe_results.jsonl，可中断续跑。--force 重跑全部。
"""
from __future__ import annotations

import inspect
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.akshare_client import AkshareClient

PERIODS = ["20251231", "20250930", "20250630", "20250331"]
SAMPLE_CODE = "002594"   # 比亚迪

# 3.1 节接口对照表
# 顺序：已缓存的不论位置都会跳过；未缓存的按 快速单公司→不确定→慢批量 排列，
# 保证中断续跑时优先拿到关键接口（R2/P4/P7）的真实结果。
PROBES = [
    # --- 已探测（保留在列表里以便 summary 顺序；resume 会跳过）---
    {"name": "A股代码简称全表", "fn": "stock_info_a_code_name", "params": {}, "core": "canonical ID"},
    {"name": "个股基本信息", "fn": "stock_individual_info_em", "params": {"symbol": SAMPLE_CODE}},
    {"name": "十大流通股东明细(批量,核心)", "fn": "stock_gdfx_free_holding_detail_em", "params": {"date": "20251231"}, "core": "共同股东边", "retry_periods": PERIODS},
    {"name": "十大股东(个股)", "fn": "stock_gdfx_top_10_em", "params": {"symbol": SAMPLE_CODE}},
    {"name": "十大流通股东(个股)", "fn": "stock_gdfx_free_top_10_em", "params": {"symbol": SAMPLE_CODE}},
    {"name": "股东持股分析", "fn": "stock_gdfx_holding_analyse_em", "params": {"date": "20251231"}, "retry_periods": PERIODS},
    # --- 未探测·快速单公司（关键接口优先）---
    {"name": "实控人持股变动(R2关键)", "fn": "stock_hold_control_cninfo", "params": {"symbol": SAMPLE_CODE}, "core": "R2 同一控制"},
    {"name": "高管持股变动明细", "fn": "stock_hold_management_detail_cninfo", "params": {"symbol": SAMPLE_CODE}},
    {"name": "股东人数", "fn": "stock_hold_num_cninfo", "params": {"symbol": SAMPLE_CODE}},
    {"name": "关联方披露(P4优先验证)", "fn": "stock_zh_a_disclosure_relation_cninfo", "params": {"symbol": SAMPLE_CODE}, "core": "P4 金标准捷径"},
    {"name": "信披公告(P4金标准)", "fn": "stock_zh_a_disclosure_report_cninfo", "params": {"symbol": SAMPLE_CODE}, "core": "P4 金标准"},
    {"name": "行业板块成分股", "fn": "stock_board_industry_cons_ths", "params": {"symbol": "汽车整车"}},
    # --- 未探测·不确定规模 ---
    {"name": "高管持股", "fn": "stock_ggcg_em", "params": {}},
    {"name": "内部交易(含董监高关系)", "fn": "stock_inner_trade_xq", "params": {}},
    # --- 未探测·慢批量（放最后，中断也不影响关键结论）---
    {"name": "股东持股变动", "fn": "stock_gdfx_free_holding_change_em", "params": {"date": "20251231"}, "retry_periods": PERIODS},
    {"name": "对外担保(R7)", "fn": "stock_cg_guarantee_cninfo", "params": {}, "core": "R7 担保关联"},
    {"name": "公司诉讼", "fn": "stock_cg_lawsuit_cninfo", "params": {}},
    {"name": "股权质押", "fn": "stock_cg_equity_mortgage_cninfo", "params": {}},
]

JSONL = Path(".cache/probe_results.jsonl")


def load_done() -> dict[str, dict]:
    done: dict[str, dict] = {}
    if JSONL.exists():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                done[obj["fn"]] = obj
            except json.JSONDecodeError:
                continue
    return done


def probe_one(client: AkshareClient, spec: dict) -> dict:
    import akshare as ak

    fn_name = spec["fn"]
    result: dict = {
        "name": spec["name"],
        "fn": fn_name,
        "core": spec.get("core", ""),
        "callable": False,
        "signature": "",
        "params_used": {},
        "columns": [],
        "n_rows": 0,
        "elapsed_s": 0.0,
        "error": "",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    fn = getattr(ak, fn_name, None)
    if fn is None:
        result["error"] = "接口不存在(该 akshare 版本无此函数)"
        return result
    result["callable"] = True
    try:
        result["signature"] = str(inspect.signature(fn))
    except (TypeError, ValueError) as e:
        result["signature"] = f"<无法获取签名: {e}>"

    attempts = [spec["params"]]
    for p in spec.get("retry_periods", []):
        patched = dict(spec["params"])
        patched["date"] = p
        if patched not in attempts:
            attempts.append(patched)

    last_err = ""
    for params in attempts:
        result["params_used"] = params
        t0 = time.perf_counter()
        try:
            df = client.get(fn_name, **params)
            result["elapsed_s"] = round(time.perf_counter() - t0, 3)
            result["columns"] = list(df.columns) if hasattr(df, "columns") else []
            result["n_rows"] = int(len(df)) if hasattr(df, "__len__") else 0
            result["error"] = ""
            return result
        except Exception as e:
            result["elapsed_s"] = round(time.perf_counter() - t0, 3)
            last_err = f"{type(e).__name__}: {e}"
            continue
    result["error"] = last_err
    return result


def append_result(r: dict) -> None:
    JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_summary(results: list[dict]) -> None:
    Path(".cache/probe_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ok = sum(1 for r in results if not r["error"])
    md = ["# P0 接口探测原始结果", ""]
    md.append(f"> 探测时间 {results[-1]['ts'] if results else '-'} | 可用 {ok}/{len(results)}")
    md.append("")
    md.append("| 接口 | 用途 | 可调用 | 行数 | 列数 | 耗时s | 错误 |")
    md.append("|---|---|---|---|---|---|---|")
    for r in results:
        err = (r["error"][:40] + "…") if len(r["error"]) > 40 else r["error"]
        md.append(
            f"| `{r['fn']}` | {r['core']} | {'是' if r['callable'] else '否'} | "
            f"{r['n_rows']} | {len(r['columns'])} | {r['elapsed_s']} | {err} |"
        )
    md.append("")
    md.append("## 各接口列名")
    for r in results:
        md.append(f"### `{r['fn']}` ({r['name']})")
        md.append(f"- 签名: `{r['signature']}`")
        md.append(f"- 参数: `{r['params_used']}`")
        md.append(f"- 列名({len(r['columns'])}): {r['columns']}")
        if r["error"]:
            md.append(f"- 错误: {r['error']}")
        md.append("")
    Path("docs/data-probe-raw.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n汇总: {ok}/{len(results)} 接口可用")


def main(force: bool = False) -> None:
    client = AkshareClient()
    done = {} if force else load_done()
    if done:
        print(f"已探测 {len(done)} 个，续跑剩余\n")

    for spec in PROBES:
        fn = spec["fn"]
        if fn in done:
            print(f"跳过(已探测): {fn}")
            continue
        print(f"探测: {fn} ...", flush=True)
        r = probe_one(client, spec)
        status = "OK" if not r["error"] else "FAIL"
        print(f"  -> {status} | rows={r['n_rows']} | cols={len(r['columns'])} | {r['elapsed_s']}s")
        if r["error"]:
            print(f"     {r['error'][:120]}")
        append_result(r)
        done[fn] = r

    write_summary(list(done.values()))


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
