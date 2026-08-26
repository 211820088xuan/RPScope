"""P9 CLI - 输入股票代码, 产出 JSON + HTML 底稿。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.report.dossier import build_dossier
from src.report.render import render_html
from src.report.writer import write_prose
from src.rules.engine import RuleEngine
from src.store.db import Store


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python make_report.py <stock_code> [--prose]"); return
    code = sys.argv[1]
    store = Store("rpscope.db")
    eng = RuleEngine("config/rules.yaml")
    d = build_dossier(store, eng, code)
    out = Path(f"reports/{code}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "dossier.json").write_text(json.dumps(d, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / "dossier.html").write_text(render_html(d), encoding="utf-8")
    print(f"JSON -> {out/'dossier.json'}")
    print(f"HTML -> {out/'dossier.html'}")
    print(f"\n关联方: matched={d['related']['n_matched']} system_only={d['related']['n_system_only']} gold_only={d['related']['n_gold_only']}")
    print(f"事件 {len(d['events'])} 条")
    if "--prose" in sys.argv:
        from src.llm.client import LLMClient
        prose = write_prose(d, LLMClient(), use_llm=True)
        (out / "dossier.md").write_text(prose, encoding="utf-8")
        print(f"Prose(MD) -> {out/'dossier.md'}")
    store.close()


if __name__ == "__main__":
    main()
