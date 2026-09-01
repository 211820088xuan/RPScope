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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.agent.graph import run as agent_run
from src.llm.client import LLMClient
from src.query.pipeline import run as nlq_run
from src.report.dossier import build_dossier
from src.report.pdf_export import render_pdf
from src.report.writer import write_prose
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

# T8: 启动健康检查 — graph.pkl 必须存在且可加载
def _startup_health_check():
    import os, sys
    graph_path = ".cache/graph.pkl"
    if not os.path.exists(graph_path):
        print(f"[FATAL] graph.pkl not found at {graph_path}", file=sys.stderr)
        print(f"[HINT] Run: py scripts/rebuild_graph.py", file=sys.stderr)
        raise SystemExit(1)
    try:
        import pickle
        with open(graph_path, "rb") as f:
            pickle.load(f)
    except Exception as e:
        print(f"[FATAL] graph.pkl corrupt: {e}", file=sys.stderr)
        print(f"[HINT] Run: py scripts/rebuild_graph.py", file=sys.stderr)
        raise SystemExit(1)

_startup_health_check()

# T9: 输入长度上限
MAX_INPUT_LEN = 500

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
    if len(q) > MAX_INPUT_LEN:
        raise HTTPException(400, f"输入过长({len(q)}字符), 上限{MAX_INPUT_LEN}字")
    if not body.get("nocache"):
        cached = _cache.get(q)
        if cached is not None:
            cached["cache_hit"] = True
            return dict(cached)
    s = _store()
    try:
        r = nlq_run(s, _eng, _llm, q, body.get("context_code",""), body.get("session_id",""))
    finally:
        s.close()
    out = {"intent": r["intent"], "answer": r["answer"], "used_llm": r["used_llm"],
           "verify": r["verify"], "elapsed_ms": r["elapsed_ms"], "cache_hit": False,
           "clarifications": r.get("clarifications", []),
           "coreference": r.get("coreference", {})}
    _cache.set(q, out)
    return out


@app.get("/api/stats")
def stats():
    return {"cache": _cache.snapshot(), "traces": trace_snapshot()}


@app.get("/api/report/{code}/pdf")
def report_pdf(code: str):
    s = _store()
    try:
        d = build_dossier(s, _eng, code)
        from fastapi.responses import Response
        from io import BytesIO
        buf = BytesIO()
        render_pdf(d, buf)
        return Response(content=buf.getvalue(), media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename={code}_dossier.pdf"})
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        s.close()


@app.get("/api/report/{code}/prose")
def report_prose(code: str):
    s = _store()
    try:
        d = build_dossier(s, _eng, code)
        prose = write_prose(d, _llm, use_llm=True)
        return {"prose": prose, "used_llm": _llm.enabled}
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        s.close()


@app.get("/api/ask/stream")
def ask_stream(q: str, context_code: str = "", session_id: str = ""):
    """SSE 流式问答: stage → coreference → data → token → verify → done。"""
    if len(q) > MAX_INPUT_LEN:
        return JSONResponse({"error": f"输入过长({len(q)}字符), 上限{MAX_INPUT_LEN}字"}, status_code=400)
    import json, time as _time, uuid
    from src.query.pipeline import run as nlq_run
    from src.query.intent import classify as rule_classify
    from src.query.rule_slots import rule_extract
    from src.query.entity_link import link_slots
    from src.query.templates import get_executor
    from src.agent.verifier import verify_answer
    from src.query.conversation import get_session
    from src.query.coreference import resolve_with_llm_fallback

    def event_gen():
        t0 = _time.perf_counter()
        s = _store()
        try:
            # 1. 规则分类
            r = rule_classify(q)
            intent = r["intent"]
            yield f"event: stage\ndata: {json.dumps({'stage': 'classify', 'intent': intent, 'confidence': r['confidence']}, ensure_ascii=False)}\n\n"

            # 1.5 指代消解(多轮)
            sid = session_id or str(uuid.uuid4())[:8]
            conv = get_session(sid)
            test_slots = rule_extract(intent, q, s.conn, context_code)
            has_entity = test_slots is not None and bool(
                test_slots.get("company") or test_slots.get("entity") or
                test_slots.get("entity_a") or test_slots.get("company_a"))
            coref = resolve_with_llm_fallback(q, conv, has_entity, _llm, s.conn)
            if coref.get("resolved"):
                entity = coref["entity"]
                yield f"event: coreference\ndata: {json.dumps({'resolved': True, 'target': entity.get('name',''), 'pronoun': coref.get('pronoun',''), 'source': coref.get('source','')}, ensure_ascii=False)}\n\n"
                # 注入指代解出的实体到 slots
                code = entity.get("stock_code", "")
                if code and intent in ("Q1","Q4","Q5"):
                    slots = {"company": code}
                elif intent == "Q3" and entity.get("entity_id"):
                    slots = {"entity": entity["entity_id"]}
                else:
                    slots = test_slots or {}
            elif coref.get("clarify"):
                yield f"event: clarify\ndata: {json.dumps({'message': coref['clarify'], 'candidates': coref.get('candidates', [])}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps({'elapsed_ms': 0}, ensure_ascii=False)}\n\n"
                return
            else:
                # 2. 槽位抽取(规则)
                slots = test_slots or {}
                if not slots and intent in ("Q1","Q4","Q5") and context_code:
                    slots = {"company": context_code}

            yield f"event: stage\ndata: {json.dumps({'stage': 'slot_fill', 'slots': {k:v for k,v in slots.items() if not k.startswith('_')}, 'source': 'rule'}, ensure_ascii=False)}\n\n"

            # 3. 实体链接(指代已解的跳过)
            if slots.get("_coref"):
                linked = {"slots": slots, "clarifications": [], "errors": []}
            else:
                linked = link_slots(s, intent, slots)
            yield f"event: stage\ndata: {json.dumps({'stage': 'entity_link', 'clarifications': linked['clarifications']}, ensure_ascii=False)}\n\n"

            # 4. 模板执行 → 推结构化结果(LLM 之前)
            if intent != "Q7" and not linked["clarifications"] and not linked["errors"]:
                executor = get_executor(intent)
                result = executor(s, _eng, linked["slots"])
                yield f"event: data\ndata: {json.dumps(result, ensure_ascii=False, default=str)}\n\n"

                # 记录对话轮次(更新焦点栈)
                result_entities = []
                if "parties" in result:
                    result_entities = [{"name": p.get("name",""), "stock_code": p.get("code","")} for p in result.get("parties",[])[:10]]
                elif "results" in result:
                    result_entities = [{"name": r2.get("short_name",""), "stock_code": r2.get("stock_code","")} for r2 in result.get("results",[])[:10]]
                linked_entities = [{"stock_code": slots.get("company",""), "name": slots.get("_company_name","")}] if slots.get("company") else []
                conv.record_turn(question=q, intent=intent, slots=slots,
                                linked_entities=linked_entities,
                                result_entities=result_entities)

                # 5. LLM 流式生成回答
                if _llm.enabled:
                    yield f"event: stage\ndata: {json.dumps({'stage': 'generate'}, ensure_ascii=False)}\n\n"
                    ctx = json.dumps(result, ensure_ascii=False, default=str)[:3000]
                    code = linked["slots"].get("company", context_code)
                    try:
                        full_answer = ""
                        for token in _llm.chat_stream([
                            {"role": "system", "content": f"你是关联方分析助手。用户正在查看股票 {code}。基于结构化查询结果回答, 用中文。财务和行业分析可以基于你的知识。不要加免责声明。"},
                            {"role": "user", "content": f"问题: {q}\n\n查询结果:\n{ctx}"},
                        ]):
                            full_answer += token
                            yield f"event: token\ndata: {json.dumps({'text': token}, ensure_ascii=False)}\n\n"

                        # 6. 回查
                        v = verify_answer(s, full_answer)
                        yield f"event: verify\ndata: {json.dumps({'passed': v['passed'], 'violations': v.get('violations',[])}, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        yield f"event: error\ndata: {json.dumps({'error': str(e)[:100]}, ensure_ascii=False)}\n\n"
                else:
                    yield f"event: token\ndata: {json.dumps({'text': json.dumps(result, ensure_ascii=False, default=str)[:500]}, ensure_ascii=False)}\n\n"
                    yield f"event: verify\ndata: {json.dumps({'passed': True}, ensure_ascii=False)}\n\n"
            else:
                # Q7 或有澄清 → 退回非流式
                r2 = nlq_run(s, _eng, _llm, q, context_code)
                yield f"event: data\ndata: {json.dumps({'answer': r2['answer'][:500], 'clarifications': r2.get('clarifications', [])}, ensure_ascii=False)}\n\n"
                yield f"event: verify\ndata: {json.dumps({'passed': r2.get('verify',{}).get('passed', True)}, ensure_ascii=False)}\n\n"

            elapsed = (_time.perf_counter() - t0) * 1000
            yield f"event: done\ndata: {json.dumps({'elapsed_ms': round(elapsed)}, ensure_ascii=False)}\n\n"
        finally:
            s.close()

    return StreamingResponse(event_gen(), media_type="text/event-stream")


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
