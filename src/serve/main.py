"""P9 FastAPI 服务 - /api/report /api/company /api/ask + 静态前端。

无 LLM 依赖(底稿模板/规则引擎确定性); /api/ask 的 open_qa 才用 LLM(慢)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.agent.graph import run as agent_run
from src.llm.client import LLMClient
from src.report.dossier import build_dossier
from src.rules.engine import RuleEngine
from src.serve.cache import QueryCache
from src.serve.observability import clear as trace_clear, snapshot as trace_snapshot
from src.store.db import Store

app = FastAPI(title="RPScope")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_store = Store("rpscope.db")
_eng = RuleEngine("config/rules.yaml")
_llm = LLMClient()
_cache = QueryCache()

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


@app.get("/api/company/{code}")
def company(code: str):
    co = _store.conn.execute("SELECT * FROM company WHERE stock_code=?", (code.zfill(6),)).fetchone()
    return dict(co) if co else {}


@app.get("/api/report/{code}")
def report(code: str):
    try:
        d = build_dossier(_store, _eng, code)
        return d
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/ask")
def ask(body: dict):
    q = body.get("question", "")
    if not q:
        raise HTTPException(400, "question required")
    cached = _cache.get(q)
    if cached is not None:
        cached["cache_hit"] = True
        return cached
    r = agent_run(_store, _eng, _llm, q)
    out = {"intent": r["intent"], "answer": r["answer"], "used_llm": r["used_llm"],
            "verify": r["verify"], "elapsed_ms": r["elapsed_ms"], "cache_hit": False}
    _cache.set(q, out)
    return out


@app.get("/api/stats")
def stats():
    return {"cache": _cache.snapshot(), "traces": trace_snapshot()}


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


# 静态前端文件
if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")
