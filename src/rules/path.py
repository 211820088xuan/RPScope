"""P3 路径转可读 dict - 每跳含起点/终点/边类型/关键属性。"""
from __future__ import annotations


def make_hop(frm: str, to: str, edge: str, **attrs) -> dict:
    return {"from": frm, "to": to, "edge": edge, "attrs": {k: v for k, v in attrs.items() if v is not None}}


def render_path(path: list[dict]) -> str:
    """人可读的路径串, 供底稿展示。"""
    if not path:
        return ""
    parts = []
    for hop in path:
        a = hop.get("attrs", {})
        extra = ""
        if "ratio" in a:
            extra = f" [{a['ratio']}%]"
        elif "title" in a:
            extra = f" [{a['title']}]"
        parts.append(f"{hop['from']} -{hop['edge']}{extra}-> {hop['to']}")
    return " | ".join(parts)
