"""读人工填好的 system_only_review.csv, 统计三分类占比 + 修正后 precision。

修正逻辑: true_omission(真漏报)计入 TP(系统发现年报未披露的实质关联=系统价值),
  reasonable_undisclosed + system_error 仍算 FP。
修正后 P = (原 matched + true_omission) / (原 matched + 原 system_only)。
"""
import csv, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CSV_PATH = Path("data/reviews/system_only_review.csv")


def main():
    if not CSV_PATH.exists():
        print(f"无核查表 {CSV_PATH}"); return
    rows = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # 跳过判定标准说明行(第二行 human_class 有长文本)
        for r in reader:
            hc = (r.get("human_class") or "").strip()
            if hc in ("true_omission", "reasonable_undisclosed", "system_error"):
                rows.append(r)
    if not rows:
        print(f"CSV 有 {sum(1 for _ in open(CSV_PATH, encoding='utf-8-sig'))-1} 行, 但 human_class 全空。")
        print("人工填写 human_class 后再跑此脚本。")
        print("判定标准: true_omission(真漏报) / reasonable_undisclosed(合理未披露) / system_error(误报)")
        return

    from collections import Counter
    counts = Counter(r["human_class"] for r in rows)
    n = len(rows)
    true_omission = counts.get("true_omission", 0)
    reasonable = counts.get("reasonable_undisclosed", 0)
    errors = counts.get("system_error", 0)

    # 从 eval-v1.md 或 DB 取基线指标
    # 基线: comparable 口径 matched + sys_only
    # 简化: 用核查表覆盖率外推
    # 修正后 P = (matched + true_omission外推) / (matched + sys_only)
    # 这里用核查样本的比例外推到全量 system_only
    print(f"=== 人工核查结果 ({n} 条) ===")
    print(f"  true_omission(真漏报): {true_omission} ({true_omission/n*100:.0f}%)")
    print(f"  reasonable_undisclosed: {reasonable} ({reasonable/n*100:.0f}%)")
    print(f"  system_error(误报): {errors} ({errors/n*100:.0f}%)")

    # 从 docs/eval-v1.md 读取基线 comparable 指标
    # 简化: 硬编码已知基线(comparable 口径)
    base_matched = 14  # 从 run_eval 输出
    base_sys_only = 213  # comparable sys_only
    # 外推: 全量 sys_only 中 true_omission 占比 = 样本占比
    ratio = true_omission / n if n else 0
    est_true_omission = int(base_sys_only * ratio)
    corrected_tp = base_matched + est_true_omission
    corrected_fp = base_sys_only - est_true_omission
    corrected_p = corrected_tp / (corrected_tp + corrected_fp) if (corrected_tp + corrected_fp) else 0
    print(f"\n=== 修正后 precision(可比口径) ===")
    print(f"  基线 P = {base_matched}/{base_matched+base_sys_only} = {base_matched/(base_matched+base_sys_only)*100:.1f}%")
    print(f"  外推 true_omission = {est_true_omission} (样本 {true_omission}/{n} → 全量 {base_sys_only})")
    print(f"  修正后 P = ({base_matched}+{est_true_omission})/({base_matched}+{base_sys_only}) = {corrected_p*100:.1f}%")
    print(f"  变化: {(corrected_p - base_matched/(base_matched+base_sys_only))*100:+.1f}pp")


if __name__ == "__main__":
    main()
