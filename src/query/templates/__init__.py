"""模板注册 — 意图ID → 执行函数。"""
from __future__ import annotations
from src.query.templates import q1_related_party, q2_relation_path, q3_reverse_control, q4_company_role, q5_risk_events, q6_overlap, q7_generated

_REGISTRY = {
    "Q1": q1_related_party,
    "Q2": q2_relation_path,
    "Q3": q3_reverse_control,
    "Q4": q4_company_role,
    "Q5": q5_risk_events,
    "Q6": q6_overlap,
    "Q7": q7_generated,
}


def get_executor(template_id: str):
    mod = _REGISTRY.get(template_id)
    if not mod:
        raise ValueError(f"unknown template: {template_id}")
    return mod.execute
