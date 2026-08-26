"""P9 FastAPI 服务 - /api/report /api/company /api/ask + 静态前端。

无 LLM 依赖(底稿模板/规则引擎确定性); /api/ask 的 open_qa 才用 LLM(慢)。
Store 每请求新开(彻底免疫 SQLite 跨线程, 不依赖 check_same_thread 也不依赖进程启动时机)。
"""
from __future__ import annotations

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

# 无状态/线程安全的单例; Store 每请求开(见 _store())
_eng = RuleEngine("config/rules.yaml")
_llm = LLMClient()
_cache = QueryCache()

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


def _store() -> Store:
    """每请求开新 Store: 开在处理该请求的线程里, 天然同线程, 彻底免疫跨线程问题。"""
    return Store("rpscope.db")


@app.get("/api/company/{code}")
def company(code: str):
    s = _store()
    try:
        co = s.conn.execute("SELECT * FROM company WHERE stock_code=?", (code.zfill(6),)).fetchone()
        return dict(co) if co else {}
    finally:
        s.close()


@app.get("/api/report/{code}")
def report(code: str):
    s = _store()
    try:
        return build_dossier(s, _eng, code)
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        s.close()


@app.post("/api/ask")
def ask(body: dict):
    q = body.get("question", "")
    if not q:
        raise HTTPException(400, "question required")
    cached = _cache.get(q)
    if cached is not None:
        cached["cache_hit"] = True
        return dict(cached)
    s = _store()
    try:
        r = agent_run(s, _eng, _llm, q)
    finally:
        s.close()
    out = {"intent": r["intent"], "answer": r["answer"], "used_llm": r["used_llm"],
           "verify": r["verify"], "elapsed_ms": r["elapsed_ms"], "cache_hit": False}
    _cache.set(q, out)
    return out


@app.get("/api/stats")
def stats():
    return {"cache": _cache.snapshot(), "traces": trace_snapshot()}


@app.get("/api/random")
def random_company():
    """随机一家有实控人数据的公司(保证底稿有内容)。"""
    s = _store()
    try:
        row = s.conn.execute(
            "SELECT stock_code, short_name FROM company WHERE stock_code IN "
            "(SELECT DISTINCT stock_code FROM actual_controller) "
            "ORDER BY RANDOM() LIMIT 1").fetchone()
        return dict(row) if row else {}
    finally:
        s.close()


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")
