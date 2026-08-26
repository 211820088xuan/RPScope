"""P9 HTML 渲染 - dossier -> 可读 HTML 报告。"""
from __future__ import annotations


def render_html(d: dict) -> str:
    co = d.get("basic", {})
    css = "body{font-family:'Microsoft YaHei',sans-serif;max-width:900px;margin:20px auto;color:#222;line-height:1.6}"
    sec = "h2{border-left:4px solid #6c3;padding-left:8px;margin-top:24px}"
    cand = ".c{margin:4px 0;padding:6px;border-left:3px solid #ccc}.high{border-color:#5a5}.medium{border-color:#c93}.low{border-color:#999}.warn{color:#c33}"
    rows = []
    rows.append(f"<html><head><meta charset=utf-8><style>{css};{sec};{cand}</style></head><body>")
    rows.append(f"<h1>{co.get('short_name','')}({co.get('stock_code','')}) 关联方与风险底稿</h1>")
    # 一
    rows.append("<h2>一、基本信息</h2>")
    rows.append(f"<p>股票代码 {co.get('stock_code','')} | 简称 {co.get('short_name','')} | 行业 {co.get('industry','') or '未知'}</p>")
    # 二
    rows.append("<h2>二、股权结构</h2><p><b>前十大股东(非通道):</b></p><ul>")
    for h in d.get("holders", [])[:10]:
        rows.append(f"<li>{h.get('holder_rank')}. {h.get('display_name')} {h.get('ratio')}% ({h.get('entity_type')})</li>")
    rows.append("</ul>")
    if d.get("controllers"):
        rows.append("<p><b>实际控制人:</b></p><ul>")
        for c in d["controllers"]:
            rows.append(f"<li>{c.get('display_name')} ({c.get('control_ratio')}%)</li>")
        rows.append("</ul>")
    # 三
    r = d.get("related", {})
    rows.append("<h2>三、关联方清单</h2>")
    rows.append(f"<h3>3.1 已披露且系统验证: {r.get('n_matched',0)} 条</h3><ul>")
    for m in r.get("matched", [])[:10]:
        rows.append(f"<li>{m['name']}</li>")
    rows.append(f"</ul><h3>3.2 系统发现·待核查: {r.get('n_system_only',0)} 条 <span class=warn>← 核心价值区</span></h3><ul>")
    for s in r.get("system_only", [])[:20]:
        rows.append(f"<li class='c {s.get('confidence','')}'><b>[{s['confidence']}]</b> {s['name']} &lt;- {s['rule']}<br><small>路径: {s.get('path','')[:100]}</small></li>")
    rows.append(f"</ul><h3>3.3 年报披露但系统未验证: {r.get('n_gold_only',0)} 条 <span class=warn>← 诚实呈现盲区</span></h3><ul>")
    for g in r.get("gold_only", [])[:10]:
        rows.append(f"<li>{g['name']}</li>")
    rows.append("</ul>")
    # 四
    rows.append("<h2>四、风险事件时间线</h2><ul>")
    for e in d.get("events", [])[:15]:
        rows.append(f"<li>{e.get('event_type')} | {e.get('event_date') or '?'} | {e.get('summary','')[:40]} | amt={e.get('amount')}</li>")
    rows.append("</ul>")
    # 五
    disc = d.get("disclaimer", {})
    rows.append("<h2>五、口径与限制</h2><ul>")
    for k in ("data_sources", "report_period", "coverage", "known_limits", "disclaimer"):
        rows.append(f"<li><b>{k}:</b> {disc.get(k,'')}</li>")
    rows.append("</ul>")
    rows.append("</body></html>")
    return "".join(rows)
