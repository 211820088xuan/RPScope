"""P4 关联方抽取 - 表格优先(pymupdf find_tables), 文本兜底 LLM, 启发式补全。

表格是确定性提取(关联方清单通常是表); 文本段用 GLM 但断言回查防幻觉。
每条标来源页码 + source_type(table/llm/heuristic)。
"""
from __future__ import annotations

from pathlib import Path

from src.gold.pdf_text import get_all_text, get_tables
from src.llm.client import LLMClient
from src.normalize.name import normalize_name, org_match_key

ORG_SUFFIX_RE = r"(?:有限公司|股份有限公司|有限责任公司|集团|企业|事务所|中心|合伙企业|研究院|厂|学校|医院|协会|基金会)"

# 财务报表科目名(误抓表时常见), 过滤掉
_FIN_STOP = {"应收账款", "合同资产", "预付款项", "其他应收款", "长期应收款", "其他非流动资产",
             "应付账款", "预收款项", "其他应付款", "长期应付款", "存货", "固定资产",
             "无形资产", "在建工程", "货币资金", "交易性金融资产", "营业收入", "营业成本",
             "管理费用", "销售费用", "财务费用", "净利润", "资产总计", "负债合计",
             "所有者权益合计", "项目", "科目", "类别", "合计", "小计"}
# 关联方类别标签(非具体名称), 过滤掉
_CAT_STOP = {"合营企业", "联营企业", "子公司", "联营公司", "合营公司", "分公司", "本公司",
             "控股子公司", "全资子公司", "控股公司", "关联方", "母公司", "同一控制下",
             "同一母公司", "其他关联方", "主要投资者个人", "关键管理人员", "合营", "联营"}


def _find_page(name: str, pages_text: dict[int, str]) -> int | None:
    n = normalize_name(name)
    for pi, t in pages_text.items():
        if n and n in normalize_name(t):
            return pi + 1
    for pi, t in pages_text.items():
        if name in t:
            return pi + 1
    return None


def _heuristic_names(text: str) -> set[str]:
    import re
    return {m.group(1).strip() for m in
            re.finditer(rf"([^\s，。、；：""''()（）\[\]【】]{{2,30}}{ORG_SUFFIX_RE})", text)}


def _extract_from_tables(pdf_path: str | Path, pages: list[int]) -> list[dict]:
    """从表格抽取关联方名称。名称列头必须含'关联方'(避免抓到'项目名称'类财务表)。"""
    out: list[dict] = []
    for pi in pages:
        for tbl in get_tables(pdf_path, pi):
            if not tbl or len(tbl) < 2:
                continue
            header = [str(c or "").strip() for c in tbl[0]]
            # 名称列头必须含"关联方"(关联方清单表的列头是"关联方"/"关联方名称")
            name_col = None
            for ci, h in enumerate(header):
                if "关联方" in h and not any(x in h for x in ["金额", "比例", "余额", "日期", "占"]):
                    name_col = ci; break
            if name_col is None:
                continue
            rel_col = None
            for ci, h in enumerate(header):
                if "关系" in h or "性质" in h:
                    rel_col = ci; break
            for row in tbl[1:]:
                if name_col >= len(row):
                    continue
                nm = str(row[name_col] or "").strip()
                if not nm or len(nm) < 2 or nm in ("无", "/", "—", "合计", "小计") or nm in _FIN_STOP or nm in _CAT_STOP:
                    continue
                rel = str(row[rel_col] or "").strip() if rel_col is not None and rel_col < len(row) else ""
                out.append({"party_name": nm, "relation_desc": rel, "page": pi + 1, "source_type": "table"})
    return out


def extract(pdf_path: str | Path, pages: list[int], client: LLMClient | None = None,
            use_llm: bool = True) -> list[dict]:
    all_text = get_all_text(pdf_path)
    pages_text = {pi: all_text.get(pi, "") for pi in pages}
    full = "\n".join(pages_text.values())[:4000]  # 截断防超长输入 -> LLM 快+少超时

    parties: list[dict] = []
    # 1. 表格(确定性, 过滤类别/科目标签)
    parties.extend(_extract_from_tables(pdf_path, pages))

    # 2. LLM 主力(不论文本/表格, 全文抽具体名 + 断言回查), 覆盖表格只抓到类别的情况
    if use_llm and client and client.enabled and full.strip():
        prompt = (
            "从下面上市公司年报关联方章节文本里, 抽取所有被披露的关联方的具体名称(法人全称/自然人姓名/机构全称)。\n"
            "只要具体名称, 不要类别词(合营企业/联营企业/子公司等), 不要本公司自己, 不要臆造。\n"
            '输出 JSON: {"parties":[{"name":"关联方具体全称","relation":"关系(如母公司/合营/联营/同控制)"}]}\n\n'
            f"章节文本:\n{full}"
        )
        try:
            obj = client.chat_json([{"role": "user", "content": prompt}], schema_keys=["parties"])
            raw = obj.get("parties", [])
        except Exception:
            raw = []
        seen = {normalize_name(p["party_name"]) for p in parties}
        for p in raw:
            name = str(p.get("name", "")).strip()
            if not name or normalize_name(name) in seen or name in _CAT_STOP or name in _FIN_STOP:
                continue
            seen.add(normalize_name(name))
            mk = org_match_key(name)
            if not (normalize_name(name) in normalize_name(full) or (mk and mk in full) or name in full):
                continue  # 断言回查防幻觉
            page = _find_page(name, pages_text)
            parties.append({"party_name": name, "relation_desc": str(p.get("relation", "")),
                             "page": page, "source_type": "llm_extracted"})

    # 3. 启发式补全
    have = {normalize_name(p["party_name"]) for p in parties}
    for name in _heuristic_names(full):
        if normalize_name(name) not in have:
            parties.append({"party_name": name, "relation_desc": "", "page": _find_page(name, pages_text),
                             "source_type": "heuristic"})

    return parties
