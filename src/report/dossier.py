"""P9 底稿组装 - 确定性(无 LLM 默认), 结构按文档:
一基本信息 二股权结构 三关联方清单(3.1已披露验证/3.2系统发现待核查/3.3年报未验证) 四风险事件时间线 五口径与限制

3.3"系统未验证的"必放(敢于呈现漏报, 专业工具与玩具的分界)。
"""
from __future__ import annotations

from src.eval.aligner import align_one, norm_name
from src.normalize.name import normalize_name
from src.rules.engine import RuleEngine
from src.rules.path import render_path
from src.store.db import Store


def build_dossier(store: Store, engine: RuleEngine, stock_code: str, as_of: str | None = None) -> dict:
    code = stock_code.zfill(6)
    co = store.conn.execute("SELECT * FROM company WHERE stock_code=?", (code,)).fetchone()
    # 一、基本信息
    basic = dict(co) if co else {}
    # 二、股权结构(以 free_holding 为主名单, ggcg 补 ratio)
    holders = [dict(r) for r in store.conn.execute(
        "SELECT MAX(h.ratio) AS ratio, e.display_name, e.entity_type, e.is_channel, e.confidence, MIN(h.id) AS ord "
        "FROM holding h JOIN entity e ON h.entity_id=e.entity_id "
        "WHERE h.stock_code=? AND h.source IN ('stock_gdfx_free_holding_detail_em','stock_ggcg_em') "
        "GROUP BY e.entity_id, e.display_name, e.entity_type, e.is_channel, e.confidence "
        "ORDER BY MIN(h.id) LIMIT 10",
        (code,)).fetchall()]
    # 补: 从 ggcg 取 ratio 填入 free_holding 的 None
    ggcg = {r['display_name']: r['ratio'] for r in store.conn.execute(
        "SELECT e.display_name, MAX(h.ratio) AS ratio FROM holding h JOIN entity e ON h.entity_id=e.entity_id "
        "WHERE h.stock_code=? AND h.source='stock_ggcg_em' AND h.ratio IS NOT NULL "
        "GROUP BY e.display_name", (code,)).fetchall()}
    for h in holders:
        if h['ratio'] is None and h['display_name'] in ggcg:
            h['ratio'] = ggcg[h['display_name']]
    controllers = [dict(r) for r in store.conn.execute(
        "SELECT ac.control_ratio, e.display_name, e.entity_type FROM actual_controller ac "
        "JOIN entity e ON ac.entity_id=e.entity_id WHERE ac.stock_code=? AND e.is_channel=0", (code,)).fetchall()]
    # 三、关联方清单(三分类)
    a = align_one(store, engine, code, as_of)
    matched = [{"name": n, "type": "已披露且系统验证"} for n in a["matched"]]
    system_only = []
    for c in a["cands"]:
        if norm_name(c.party_name) in a["matched"]:
            continue
        system_only.append({"name": c.party_name, "rule": c.rule_id, "confidence": c.confidence,
                            "path": render_path(c.path), "score": c.score,
                            "evidence": [e for e in c.evidence[:2]], "type": "系统发现·待核查"})
    gold_only = [{"name": n, "type": "年报披露但系统未验证"} for n in a["gold_only"]]

    # 四、风险事件时间线
    events = [dict(r) for r in store.conn.execute(
        "SELECT event_type, event_date, counterparty, amount, summary, source_type "
        "FROM event WHERE subject_code=? ORDER BY event_date", (code,)).fetchall()]
    # 五、口径与限制(固定)
    disclaimer = {
        "data_sources": "akshare(持股/任职/实控人/担保/诉讼/质押) + 巨潮年报(金标准)",
        "report_period": "2025-12-31(持股), 实控人/事件含历史",
        "coverage": "A 股全市场; 上行(股东/董监高/实控人)完整, 下行(子公司/联营)残缺",
        "known_limits": "批量接口无 ratio(部分); 关联方金标准含下游系统无法发现; 通道排除名单持续维护",
        "disclaimer": "本系统输出候选与证据, 不输出投资建议/评级/价值判断; 最终认定需人工判断。",
    }
    return {
        "stock_code": code, "basic": basic, "holders": holders, "controllers": controllers,
        "related": {"matched": matched, "system_only": system_only, "gold_only": gold_only,
                    "n_matched": len(matched), "n_system_only": len(system_only), "n_gold_only": len(gold_only)},
        "events": events, "disclaimer": disclaimer,
    }
