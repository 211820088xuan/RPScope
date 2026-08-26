"""RPScope P1 ETL: 缓存的 akshare DataFrame -> SQLite 事实源。

全市场入库（缓存已拉，全量比 300 家更值且 effort 相同）。
诚实记录: ratio 在批量接口缺失(NULL); 担保接口仅聚合非成对边(R7 成对需 P6 抽取)。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from src.data.akshare_client import AkshareClient
from src.normalize.name import (
    fund_match_key,
    is_channel_name,
    normalize_name,
    normalize_person,
    org_match_key,
)
from src.store.db import Store


def load_channel_cfg() -> tuple[set[str], list[re.Pattern]]:
    ce = yaml.safe_load(Path("config/rules.yaml").read_text(encoding="utf-8"))["channel_exclusion"]
    exact = set(ce.get("exact", []))
    pats = [re.compile(p) for p in ce.get("patterns", [])]
    return exact, pats


# ---- 类型推断 ----
def holder_entity_type(holder_type: str, name: str) -> str:
    t = normalize_name(holder_type)
    if "自然" in t or t == "个人" or "境内自然" in t or "境外自然" in t:
        return "person"
    if "基金" in t or "私募" in t:
        return "fund"
    if "机构" in t or "法人" in t or "企业" in t or "外资" in t:
        return "org"
    # 回退: 短名且无机构关键词 -> person
    n = normalize_name(name)
    if len(n) <= 4 and not any(k in n for k in ["公司", "基金", "银行", "证券", "保险", "集团", "信托"]):
        return "person"
    return "org"


def title_class(title: str) -> str:
    t = normalize_name(title)
    if "独立董事" in t:
        return "independent_director"
    if "监事" in t:
        return "supervisor"
    if "董事" in t:
        return "director"
    if any(k in t for k in ["总经理", "副总经理", "总裁", "副总裁", "财务", "董秘",
                            "董事会秘书", "高级管理", "总监", "首席", "总经济师", "总工程师"]):
        return "senior_mgmt"
    return "other"


def controller_entity_type(name: str) -> str:
    n = normalize_name(name)
    if any(k in n for k in ["公司", "集团", "银行", "证券", "保险", "信托", "基金", "国资委", "委员会", "管理局"]):
        return "org"
    if len(n) <= 4:
        return "person"
    return "org"


class EntityCache:
    """同一次 ingest 内 entity 去重缓存，避免重复 SELECT。"""

    def __init__(self, store: Store) -> None:
        self.store = store
        self._cache: dict[tuple[str, str], int] = {}

    def get(self, *, entity_type: str, canonical_name: str, display_name: str | None = None,
            is_channel: bool = False, raw_name: str | None = None,
            confidence: str = "medium", disambig_note: str | None = None) -> int:
        key = (entity_type, canonical_name)
        if key in self._cache:
            return self._cache[key]
        eid = self.store.get_or_create_entity(
            entity_type=entity_type, canonical_name=canonical_name, display_name=display_name,
            is_channel=is_channel, confidence=confidence, raw_name=raw_name,
            disambig_note=disambig_note,
        )
        self._cache[key] = eid
        return eid


def canonical_for(entity_type: str, name: str) -> str:
    if entity_type == "person":
        return normalize_person(name)
    if entity_type == "fund":
        return fund_match_key(name)
    return org_match_key(name)


def ingest_companies(store: Store, client: AkshareClient) -> int:
    df = client.get("stock_info_a_code_name")
    for _, r in df.iterrows():
        store.upsert_company(stock_code=str(r["code"]).zfill(6), short_name=str(r["name"]))
    store.log_ingest("stock_info_a_code_name", None, len(df))
    return len(df)


def ingest_holdings_batch(store: Store, client: AkshareClient,
                          ec: EntityCache, exact: set[str], pats: list[re.Pattern],
                          existing_cos: set[str]) -> int:
    df = client.get("stock_gdfx_free_holding_detail_em", date="20251231")
    n = 0
    for _, r in df.iterrows():
        code = str(r["股票代码"]).zfill(6)
        if code not in existing_cos:  # B股/三板等不在 A 股全表, 补建 company 保 FK
            store.upsert_company(stock_code=code, short_name=str(r.get("股票简称", code)).lstrip("*"))
            existing_cos.add(code)
        name = str(r["股东名称"])
        etype = holder_entity_type(str(r.get("股东类型", "")), name)
        canon = canonical_for(etype, name)
        ch = is_channel_name(name, exact, pats)
        eid = ec.get(entity_type=etype, canonical_name=canon, display_name=name,
                     is_channel=ch, raw_name=name, confidence="high" if not ch else "medium")
        store.upsert_holding(
            entity_id=eid, stock_code=code,
            report_period=str(r["报告期"])[:10], shares=_f(r["期末持股-数量"]),
            ratio=None, holder_rank=_i(r["序号"]), source="stock_gdfx_free_holding_detail_em",
            valid_from=str(r["报告期"])[:10], valid_to=None,
        )
        n += 1
    store.log_ingest("stock_gdfx_free_holding_detail_em", "20251231", n)
    return n


def ingest_holdings_ggcg(store: Store, client: AkshareClient, ec: EntityCache,
                         existing_cos: set[str]) -> int:
    """高管持股变动 -> 以 变动人 为 person 实体 + holding(含 ratio)。"""
    df = client.get("stock_ggcg_em")
    n = 0
    for _, r in df.iterrows():
        code = str(r["代码"]).zfill(6)
        if code not in existing_cos:
            store.upsert_company(stock_code=code, short_name=str(r.get("名称", code)).lstrip("*"))
            existing_cos.add(code)
        name = str(r["股东名称"])
        if not name or name == "nan":
            continue
        canon = normalize_person(name)
        eid = ec.get(entity_type="person", canonical_name=canon, display_name=name,
                     raw_name=name, confidence="medium")
        store.upsert_holding(
            entity_id=eid, stock_code=code,
            report_period=str(r.get("变动截止日") or r.get("公告日") or "")[:10],
            shares=_f(r["变动后持股情况-持股总数"]),
            ratio=_f(r["变动后持股情况-占总股本比例"]), holder_rank=None,
            source="stock_ggcg_em", valid_from=str(r.get("变动开始日") or "")[:10],
            valid_to=None,
        )
        n += 1
    store.log_ingest("stock_ggcg_em", None, n)
    return n


def _strip_code_prefix(code: str) -> str:
    """剥离 SH/SZ/BJ 等字母前缀, 保留 6 位数字代码。inner_trade 的 股票代码 带 SH/SZ 前缀需统一。"""
    import re
    code = re.sub(r"^[A-Za-z]+", "", str(code)).strip()
    return code.zfill(6)


def ingest_positions(store: Store, client: AkshareClient, ec: EntityCache,
                     name2code: dict[str, str], existing_cos: set[str]) -> int:
    """内部交易 -> person + position(职务)。股票代码缺失时按名称补, 并统一剥前缀。"""
    df = client.get("stock_inner_trade_xq")
    n = 0
    for _, r in df.iterrows():
        code = str(r.get("股票代码") or "").strip()
        sname = str(r.get("股票名称", ""))
        if not code or code == "nan":
            code = name2code.get(normalize_name(sname), "")
        if not code:
            continue
        code = _strip_code_prefix(code)
        if code not in existing_cos:
            store.upsert_company(stock_code=code, short_name=sname.lstrip("*"))
            existing_cos.add(code)
        person = str(r["变动人"])
        canon = normalize_person(person)
        eid = ec.get(entity_type="person", canonical_name=canon, display_name=person,
                     raw_name=person, confidence="low")
        title = str(r.get("董监高职务") or "")
        if not title or title == "nan":
            continue
        store.upsert_position(
            entity_id=eid, stock_code=code, title=title, title_class=title_class(title),
            source="stock_inner_trade_xq", valid_from=str(r.get("变动日期") or "")[:10],
            valid_to=None,
        )
        n += 1
    store.log_ingest("stock_inner_trade_xq", None, n)
    return n


def ingest_controllers(store: Store, client: AkshareClient, ec: EntityCache,
                       existing_cos: set[str]) -> int:
    """实控人: '实际控制人持股变动' 列(名不副实, 含控制人名, \\r/; 分隔) 取首 token。"""
    df = client.get("stock_hold_control_cninfo", symbol="全部")
    # 列名逐版本漂移 -> 用 normalize_name 稳健匹配
    # 真实列(逐字节验证): 证券代码/证券简称/变动日期/实际控制人名称/控股数量/控股比例/直接控制人名称/控制类型
    colmap = {normalize_name(c): c for c in df.columns}
    col_actual = colmap.get(normalize_name("实际控制人名称"))
    col_code = colmap.get(normalize_name("证券代码"))
    col_sname = colmap.get(normalize_name("证券简称"))
    col_date = colmap.get(normalize_name("变动日期"))
    col_ratio = colmap.get(normalize_name("控股比例"))
    col_type = colmap.get(normalize_name("控制类型"))
    n = 0
    PLACEHOLDERS = {"无", "无实际控制人", "不详", "未知", "不适用", "—", "-", "无实际控制", "无实控人", "空"}
    for _, r in df.iterrows():
        if not col_actual or not col_code:
            break
        code = str(r[col_code]).zfill(6)
        if code == "nan" or not code:
            continue
        if code not in existing_cos:
            store.upsert_company(stock_code=code, short_name=str(r.get(col_sname, code) if col_sname else code).lstrip("*"))
            existing_cos.add(code)
        raw = str(r.get(col_actual, "") or "")
        # 值可能是控制链多 token (顾雄军;力源股份;...), 取首 token 作终极控制人
        tokens = [t.strip() for t in re.split(r"[\r\n;]+", raw) if t.strip()]
        if not tokens:
            continue
        ctrl = tokens[0]
        if ctrl in PLACEHOLDERS:  # "无"/"不详" 是未披露占位, 不作控制人实体
            continue
        etype = controller_entity_type(ctrl)
        canon = canonical_for(etype, ctrl)
        note = f"控制类型={r.get(col_type)}; chain_tokens={len(tokens)}" if col_type else None
        eid = ec.get(entity_type=etype, canonical_name=canon, display_name=ctrl,
                     raw_name=ctrl, confidence="high", disambig_note=note)
        store.upsert_controller(
            stock_code=code, entity_id=eid,
            control_ratio=_f(r.get(col_ratio)) if col_ratio else None,
            source="stock_hold_control_cninfo",
            valid_from=str(r.get(col_date) or "")[:10] if col_date else None,
            valid_to=None,
        )
        n += 1
    store.log_ingest("stock_hold_control_cninfo", None, n)
    return n


def _f(v) -> float | None:
    try:
        if v is None:
            return None
        import math
        f = float(v)
        return None if (isinstance(f, float) and math.isnan(f)) else f
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


def main() -> None:
    store = Store("rpscope.db")
    client = AkshareClient()
    exact, pats = load_channel_cfg()
    ec = EntityCache(store)

    # 名称->代码 映射(补 inner_trade 缺失的股票代码)
    co = client.get("stock_info_a_code_name")
    name2code = {normalize_name(n): str(c).zfill(6) for c, n in zip(co["code"], co["name"])}

    print("ingest companies ..."); n_co = ingest_companies(store, client); store.commit(); print(f"  {n_co}")
    existing_cos = {r[0] for r in store.conn.execute("SELECT stock_code FROM company")}
    print("ingest holdings(batch) ..."); n_h = ingest_holdings_batch(store, client, ec, exact, pats, existing_cos); store.commit(); print(f"  {n_h}")
    print("ingest holdings(ggcg, 含ratio) ..."); n_g = ingest_holdings_ggcg(store, client, ec, existing_cos); store.commit(); print(f"  {n_g}")
    print("ingest positions(inner_trade) ..."); n_p = ingest_positions(store, client, ec, name2code, existing_cos); store.commit(); print(f"  {n_p}")
    print("ingest controllers ..."); n_c = ingest_controllers(store, client, ec, existing_cos); store.commit(); print(f"  {n_c}")

    c = store.counts()
    print("\n=== 入库统计 ===")
    for k, v in c.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
