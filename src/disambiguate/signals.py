"""P2 实体消歧 - 5 信号打分。

每信号输入: 姓名 name, 两条记录 rec_a/rec_b, 全局统计 stats。
每信号输出: (score 0..1, reason str)。1=强同源, 0=强不同源。

记录结构(Record): {stock_code, title, valid_from, source}
诚实缺口: region_match 无数据(注册地未入库), 返回中性 0.5 + 标注。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class Record:
    stock_code: str
    title: str = ""
    valid_from: str = ""
    source: str = ""


@dataclass
class Stats:
    name_freq: int = 0          # 该姓名在全库出现多少条记录
    name_company_count: int = 0  # 该姓名关联多少家不同公司


def _same_period(a: str, b: str, tol_days: int = 365) -> bool | None:
    """两条 valid_from 是否在 tol_days 内。None=无法解析。"""
    try:
        da = date.fromisoformat(str(a)[:10])
        db = date.fromisoformat(str(b)[:10])
    except (ValueError, TypeError):
        return None
    return abs((da - db).days) <= tol_days


# ---- 信号 1: 姓名稀有度 ----
def name_rarity(name: str, rec_a: Record, rec_b: Record, stats: Stats) -> tuple[float, str]:
    """罕见姓名更可能是同一人; 常见名(张伟/王芳)降分。

    以 stats.name_company_count 作稀有度代理: 出现公司越多, 越可能是重名合并。
    """
    n = stats.name_company_count
    if n <= 2:
        s = 0.9
        why = f"姓名仅见{n}家, 稀有, 倾向同人"
    elif n <= 5:
        s = 0.6
        why = f"姓名见{n}家, 中等常见"
    elif n <= 20:
        s = 0.35
        why = f"姓名见{n}家, 常见, 重名可能高"
    else:
        s = 0.15
        why = f"姓名见{n}家, 极常见, 强烈怀疑重名"
    return s, why


# ---- 信号 2: 持股交叉 ----
def holding_cross(name: str, rec_a: Record, rec_b: Record, stats: Stats) -> tuple[float, str]:
    """两条都是持股变动记录 -> 同一人投资行为(弱正信号)。
    本实现: 都来自 ggcg(持股变动源) 且同期 -> +分; 一持股一任职 -> 中性。"""
    a_hold = rec_a.source in ("stock_ggcg_em", "stock_gdfx_free_holding_detail_em")
    b_hold = rec_b.source in ("stock_ggcg_em", "stock_gdfx_free_holding_detail_em")
    if a_hold and b_hold:
        sp = _same_period(rec_a.valid_from, rec_b.valid_from)
        if sp is True:
            return 0.7, "两侧均持股变动且同期, 同人投资行为"
        if sp is False:
            return 0.5, "两侧均持股但不同期"
        return 0.55, "两侧均持股, 时间不可解析"
    return 0.5, "一侧任职一侧持股或不可判定, 中性"


# ---- 信号 3: 任职广度 ----
def company_count(name: str, rec_a: Record, rec_b: Record, stats: Stats) -> tuple[float, str]:
    """该姓名关联公司总数过多 -> 单个自然人难以任职这么多, 倾向重名。"""
    n = stats.name_company_count
    if n <= 3:
        return 0.7, f"仅{n}家公司, 可一人任职"
    if n <= 10:
        return 0.5, f"{n}家公司, 边界, 需其他信号"
    return 0.2, f"{n}家公司, 远超自然人正常任职数, 强烈重名"


# ---- 信号 4: 地域一致 ----
def region_match(name: str, rec_a: Record, rec_b: Record, stats: Stats) -> tuple[float, str]:
    """公司注册地一致/相邻 -> 弱正。诚实缺口: 未入库注册地, 返回中性。"""
    return 0.5, "无注册地数据, 中性"


# ---- 信号 5: 任期时段重叠 ----
def tenure_overlap(name: str, rec_a: Record, rec_b: Record, stats: Stats) -> tuple[float, str]:
    """两条任职记录时段是否合理重叠/相邻。同期在同行业多家任职仍可能(董事兼职),
    但若时段相隔>5年且不同公司, 更可能不同人。"""
    sp = _same_period(rec_a.valid_from, rec_b.valid_from, tol_days=365 * 3)
    if sp is True:
        return 0.65, "任职时段3年内, 同人可能"
    if sp is False:
        return 0.3, "任职时段相隔>3年, 不同人可能"
    return 0.5, "时间不可解析, 中性"


SIGNALS = [name_rarity, holding_cross, company_count, region_match, tenure_overlap]
WEIGHTS = {"name_rarity": 0.25, "holding_cross": 0.25, "company_count": 0.20,
           "region_match": 0.05, "tenure_overlap": 0.25}


def score_pair(name: str, rec_a: Record, rec_b: Record, stats: Stats) -> tuple[float, dict[str, float], list[str]]:
    """加权融合。返回 (总分, 各信号分, 各理由)。"""
    parts: dict[str, float] = {}
    why: list[str] = []
    total = 0.0
    for sig in SIGNALS:
        s, reason = sig(name, rec_a, rec_b, stats)
        parts[sig.__name__] = round(s, 3)
        why.append(f"{sig.__name__}={s:.2f}({reason})")
        total += WEIGHTS[sig.__name__] * s
    return round(total, 3), parts, why
