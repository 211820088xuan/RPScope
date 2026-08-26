"""修复可挽救的失败接口：用正确参数重新探测，覆盖 jsonl 中对应条目。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data.akshare_client import AkshareClient

JSONL = Path(".cache/probe_results.jsonl")
client = AkshareClient()

# 用正确参数重新探测
fixes = [
    {"name": "实控人持股变动(R2关键)", "fn": "stock_hold_control_cninfo",
     "params": {"symbol": "全部"}, "core": "R2 同一控制"},
    {"name": "股东人数", "fn": "stock_hold_num_cninfo",
     "params": {"date": "20251231"}, "retry_periods": ["20250930","20250630"]},
    {"name": "个股基本信息", "fn": "stock_individual_info_em",
     "params": {"symbol": "002594"}, "core": ""},
    {"name": "十大股东(个股)", "fn": "stock_gdfx_top_10_em",
     "params": {"symbol": "sz002594", "date": "20251231"}},  # 加交易所前缀
]

def probe(spec):
    import akshare as ak, inspect
    fn = getattr(ak, spec["fn"], None)
    r = {"name": spec["name"], "fn": spec["fn"], "core": spec.get("core",""),
         "callable": fn is not None, "signature": str(inspect.signature(fn)) if fn else "",
         "params_used": spec["params"], "columns": [], "n_rows": 0, "elapsed_s": 0.0,
         "error": "", "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    if fn is None:
        r["error"] = "接口不存在"
        return r
    attempts = [spec["params"]]
    for p in spec.get("retry_periods", []):
        np = dict(spec["params"]); np["date"] = p; attempts.append(np)
    last = ""
    for params in attempts:
        r["params_used"] = params
        t0 = time.perf_counter()
        try:
            df = client.get(spec["fn"], **params)
            r["elapsed_s"] = round(time.perf_counter()-t0, 3)
            r["columns"] = list(df.columns) if hasattr(df,"columns") else []
            r["n_rows"] = int(len(df)) if hasattr(df,"__len__") else 0
            return r
        except Exception as e:
            r["elapsed_s"] = round(time.perf_counter()-t0, 3)
            last = f"{type(e).__name__}: {e}"
    r["error"] = last
    return r

# 读取已有，替换匹配 fn
existing = {}
for l in JSONL.read_text(encoding="utf-8").splitlines():
    if l.strip():
        o = json.loads(l); existing[o["fn"]] = o

for spec in fixes:
    print(f"重探: {spec['fn']} params={spec['params']}", flush=True)
    r = probe(spec)
    st = "OK" if not r["error"] else "FAIL"
    print(f"  -> {st} rows={r['n_rows']} cols={len(r['columns'])} {r['elapsed_s']}s")
    if r["error"]: print(f"     {r['error'][:120]}")
    if r["columns"]: print(f"     cols={r['columns']}")
    existing[r["fn"]] = r

# 回写 jsonl
JSONL.write_text("\n".join(json.dumps(existing[k], ensure_ascii=False) for k in existing) + "\n", encoding="utf-8")
# 重生成 summary
from scripts.probe import write_summary
write_summary(list(existing.values()))
print("\njsonl 与 data-probe-raw.md 已更新")
