"""P9 PDF 导出 - reportlab 生成中文 PDF 底稿。"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

# 注册 CJK 字体
try:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    CJK = "STSong-Light"
except Exception:
    CJK = "Helvetica"


def render_pdf(dossier: dict, output_path) -> Path:
    """dossier dict -> PDF 文件(接受路径或 BytesIO)。"""
    from io import BytesIO
    is_buf = hasattr(output_path, "write")
    if not is_buf:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        output_path = str(p)
    doc = SimpleDocTemplate(output_path if is_buf else str(output_path), pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=CJK, fontSize=16, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=CJK, fontSize=13, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["Normal"], fontName=CJK, fontSize=10, leading=15)
    small = ParagraphStyle("small", parent=styles["Normal"], fontName=CJK, fontSize=8, leading=12)

    co = dossier.get("basic", {})
    elems = []
    elems.append(Paragraph(f"{co.get('short_name','')}({co.get('stock_code','')}) 关联方穿透底稿", h1))
    elems.append(Spacer(1, 5))

    # 基本信息
    elems.append(Paragraph("一、基本信息", h2))
    elems.append(Paragraph(f"简称: {co.get('short_name','')}  代码: {co.get('stock_code','')}  行业: {co.get('industry','未知')}", body))
    elems.append(Spacer(1, 8))

    # 股权结构
    elems.append(Paragraph("二、股权结构 前十大股东", h2))
    holder_data = [["#", "股东", "比例", "类型"]]
    for i, h in enumerate(dossier.get("holders", [])[:10]):
        if h.get("is_channel"):
            continue
        r = h.get("ratio")
        holder_data.append([str(i+1), h.get("display_name",""), f"{r}%" if r else "未披露", h.get("entity_type","")])
    elems.append(Table(holder_data, colWidths=[15*mm, 70*mm, 25*mm, 30*mm]))
    elems.append(Spacer(1, 5))
    cs = dossier.get("controllers", [])
    elems.append(Paragraph(f"实控人: {', '.join(f'{c[\"display_name\"]}({c[\"control_ratio\"]}%)' for c in cs) if cs else '未披露'}", body))
    elems.append(Spacer(1, 8))

    # 关联方清单
    elems.append(Paragraph("三、关联方清单", h2))
    r = dossier.get("related", {})
    elems.append(Paragraph(f"已披露验证: {r.get('n_matched',0)}  系统发现待核查: {r.get('n_system_only',0)}  年报未验证: {r.get('n_gold_only',0)}", body))
    elems.append(Spacer(1, 3))
    for s in (r.get("system_only") or [])[:15]:
        elems.append(Paragraph(f"[{s.get('confidence','')}] {s.get('name','')} <- {s.get('rule','')}", small))
    elems.append(Spacer(1, 8))

    # 风险事件
    elems.append(Paragraph("四、风险事件时间线", h2))
    for e in (dossier.get("events") or [])[:10]:
        elems.append(Paragraph(f"{e.get('event_type','')} | {e.get('event_date','')} | {str(e.get('summary',''))[:40]}", small))
    elems.append(Spacer(1, 8))

    # 口径
    elems.append(Paragraph("五、口径与限制", h2))
    disc = dossier.get("disclaimer", {})
    elems.append(Paragraph(disc.get("disclaimer", ""), small))
    elems.append(Paragraph(f"数据来源: {disc.get('data_sources','')}  覆盖: {disc.get('coverage','')}", small))

    doc.build(elems)
    return p
