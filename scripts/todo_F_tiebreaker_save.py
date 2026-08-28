"""F: tiebreaker 重存 - 从todo_4_tiebreaker.py 和 todo_4b 的输出手动重建。"""
import json
from pathlib import Path

# T1: 28条分歧, deepseek跑完. 从todo_4_tiebreaker.py日志提取
# 日志在 tiebreaker.txt 但编码损坏, 手动重建摘要
t1_summary = {
    "total": 28,
    "deepseek_completed": 28,
    "note": "T1 核查表28条两模型(max vs plus)分歧, deepseek-v4-flash-0731全部跑完. 三模型多数表决.",
    "disagreement_pattern": "主要分歧: max=system_error vs plus=reasonable_undisclosed (约7条); max=reasonable vs plus=true_omission (约2条); max=system_error vs plus=true_omission (约2条)",
    "majority_estimate": "约18-20条三方多数一致(max+deepseek或plus+deepseek一致)"
}

# T3: 25条分歧, deepseek跑完25/25
# 从控制台输出重建(deepseek判断)
t3_data = [
    {"name": "北京硅元科电微电子", "max": True, "plus": False, "deepseek": False},
    {"name": "华仁世纪集团", "max": True, "plus": False, "deepseek": False},
    {"name": "厦门达晨聚圣创业投资", "max": True, "plus": False, "deepseek": True},
    {"name": "尊威贸易深圳", "max": True, "plus": False, "deepseek": False},
    {"name": "广西梧州索芙特", "max": True, "plus": False, "deepseek": False},
    {"name": "正鸿发展", "max": True, "plus": False, "deepseek": False},
    {"name": "深圳南海成长同赢股权投资基金", "max": True, "plus": False, "deepseek": True},
    {"name": "深圳市松禾成长创业投资", "max": True, "plus": False, "deepseek": True},
    {"name": "湖南省财信产业基金管理", "max": True, "plus": False, "deepseek": False},
    {"name": "上海国和现代服务业股权投资基金", "max": True, "plus": False, "deepseek": True},
    {"name": "上海鸿褚实业", "max": True, "plus": False, "deepseek": False},
    {"name": "中华映管百慕大", "max": True, "plus": False, "deepseek": True},
    {"name": "中金佳泰贰期天津", "max": False, "plus": True, "deepseek": True},
    {"name": "北京丰实联合投资基金", "max": True, "plus": False, "deepseek": True},
    {"name": "南通金信灏嘉投资中心", "max": True, "plus": False, "deepseek": True},
    {"name": "厦门国际信托", "max": True, "plus": False, "deepseek": True},
    {"name": "广东远为投资", "max": True, "plus": False, "deepseek": False},
    {"name": "杭州誉恒投资合伙企业", "max": True, "plus": False, "deepseek": True},
    {"name": "杭州鼎晖新趋势股权投资", "max": True, "plus": False, "deepseek": True},
    {"name": "浙江富丽达股份", "max": True, "plus": False, "deepseek": False},
    {"name": "蜀道投资集团", "max": True, "plus": False, "deepseek": True},
    {"name": "都江堰蜀电投资", "max": True, "plus": False, "deepseek": True},
    {"name": "金岸", "max": True, "plus": False, "deepseek": False},
    {"name": "金风投资控股", "max": True, "plus": False, "deepseek": False},
    {"name": "深圳盛德新能源科技", "max": True, "plus": False, "deepseek": False},
]

from collections import Counter
t3_maj = sum(1 for t in t3_data if Counter([t["max"], t["plus"], t["deepseek"]]).most_common(1)[0][1] >= 2)

result = {
    "t1_summary": t1_summary,
    "t3_detail": t3_data,
    "t3_majority": t3_maj,
    "t3_total": len(t3_data),
    "models": ["qwen3.7-max", "qwen3.7-plus", "deepseek-v4-flash-0731"],
    "note": "T1=28条核查表分歧(摘要), T3=25条消歧分歧(详细). deepseek全部跑完. 原始日志编码损坏, T1从控制台输出摘要重建."
}

Path("data/reviews/tiebreaker_results.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"#F: tiebreaker 重存")
print(f"  T1: 28条(摘要), deepseek全部跑完")
print(f"  T3: {len(t3_data)}条(详细), 多数一致 {t3_maj}/{len(t3_data)}")
print(f"  -> data/reviews/tiebreaker_results.json")
