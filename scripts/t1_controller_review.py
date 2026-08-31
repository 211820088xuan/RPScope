"""T1.1: 统计 actual_controller 控制人 Top50 + 标注是否被排除。"""
import sys, re, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.store.db import Store
from src.normalize.name import normalize_name

s = Store("rpscope.db")

# 加载当前排除规则
cfg = yaml.safe_load(Path("config/rules.yaml").read_text(encoding="utf-8"))["channel_exclusion"]
exact = set(cfg.get("exact", []))
pats = [re.compile(p) for p in cfg.get("patterns", [])]

def is_excluded(name):
    n = normalize_name(name) if name else ""
    if n and n in {normalize_name(x) for x in exact}:
        return True, "exact"
    for p in pats:
        for cand in (name or "", n):
            if p.search(cand or ""):
                return True, f"pattern:{p.pattern[:30]}"
    return False, ""

# 统计控制人被控公司数
rows = s.conn.execute("""
    SELECT e.display_name, COUNT(DISTINCT ac.stock_code) as n_cos
    FROM actual_controller ac
    JOIN entity e ON ac.entity_id = e.entity_id
    GROUP BY e.entity_id, e.display_name
    ORDER BY n_cos DESC
    LIMIT 50
""").fetchall()

md = ["# 控制人 Top 50 审查", ""]
md.append(f"> 总控制人实体数: {s.conn.execute('SELECT COUNT(DISTINCT entity_id) FROM actual_controller').fetchone()[0]}")
md.append(f"> 被控公司数 Top 50")
md.append("")
md.append("| # | 控制人名称 | 被控公司数 | 当前被排除? | 命中规则 |")
md.append("|---|---|---|---|---|")

excluded_count = 0
not_excluded_gov = []
for i, r in enumerate(rows, 1):
    name = r[0] or ""
    n_cos = r[1]
    excluded, rule = is_excluded(name)
    if excluded:
        excluded_count += 1
    else:
        # 标注是否看起来像政府机构
        gov_keywords = ["国资委", "国有资产", "监督管理", "管理局", "财政局", "财政厅",
                        "人民政府", "管理委员会", "证监会", "监管局", "商务部"]
        is_gov = any(k in name for k in gov_keywords)
        if is_gov:
            not_excluded_gov.append((name, n_cos))
    md.append(f"| {i} | {name[:35]} | {n_cos} | {'是' if excluded else '**否**' + (' (政府机构!)' if not excluded and any(k in name for k in gov_keywords) else '')} | {rule} |")

md.append(f"\n## 统计")
md.append(f"- Top50 中被排除: {excluded_count}/50")
md.append(f"- 未被排除的政府机构: {len(not_excluded_gov)} 个")
if not_excluded_gov:
    md.append("\n### 未被排除的政府机构（需修复）")
    md.append("| 名称 | 被控公司数 |")
    md.append("|---|---|")
    for name, n in not_excluded_gov:
        md.append(f"| {name} | {n} |")

Path("docs/controller-review.md").write_text("\n".join(md), encoding="utf-8")
print(f"-> docs/controller-review.md")
print(f"Top50: 排除{excluded_count}/50, 未排除政府机构{len(not_excluded_gov)}个")
for name, n in not_excluded_gov[:10]:
    print(f"  {name} ({n}家)")
s.close()
