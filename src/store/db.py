"""SQLite 事实源访问层 - P1 临时 store (PG 就绪后换 psycopg2 实现, 接口不变)。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


class Store:
    def __init__(self, path: str | Path = "rpscope.db") -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- company ----
    def upsert_company(self, *, stock_code: str, short_name: str,
                       full_name: str | None = None, industry: str | None = None,
                       list_date: str | None = None, market_cap: float | None = None,
                       is_st: bool = False) -> None:
        self.conn.execute(
            """INSERT INTO company(stock_code, short_name, full_name, industry, list_date, market_cap, is_st)
               VALUES(?,?,?,?,?, ?, ?)
               ON CONFLICT(stock_code) DO UPDATE SET
                 short_name=excluded.short_name, full_name=COALESCE(excluded.full_name, full_name),
                 industry=COALESCE(excluded.industry, industry), list_date=COALESCE(excluded.list_date, list_date),
                 market_cap=COALESCE(excluded.market_cap, market_cap), is_st=excluded.is_st, updated_at=datetime('now')""",
            (stock_code, short_name, full_name, industry, list_date, market_cap, int(is_st)),
        )

    # ---- entity ----
    def get_or_create_entity(
        self, *, entity_type: str, canonical_name: str, display_name: str | None = None,
        is_channel: bool = False, confidence: str = "medium",
        raw_name: str | None = None, disambig_note: str | None = None,
    ) -> int:
        row = self.conn.execute(
            "SELECT entity_id, raw_names FROM entity WHERE entity_type=? AND canonical_name=?",
            (entity_type, canonical_name),
        ).fetchone()
        if row is None:
            raw_names = json.dumps([raw_name or display_name or canonical_name], ensure_ascii=False)
            cur = self.conn.execute(
                """INSERT INTO entity(entity_type, canonical_name, display_name, raw_names, is_channel, confidence, disambig_note)
                   VALUES(?,?,?,?,?,?,?)""",
                (entity_type, canonical_name, display_name, raw_names, int(is_channel), confidence, disambig_note),
            )
            return int(cur.lastrowid)
        # 追加新写法
        names = json.loads(row["raw_names"] or "[]")
        if raw_name and raw_name not in names:
            names.append(raw_name)
            self.conn.execute("UPDATE entity SET raw_names=? WHERE entity_id=?",
                              (json.dumps(names, ensure_ascii=False), row["entity_id"]))
        if is_channel:
            self.conn.execute("UPDATE entity SET is_channel=1 WHERE entity_id=?", (row["entity_id"],))
        return int(row["entity_id"])

    # ---- holding ----
    def upsert_holding(self, *, entity_id: int, stock_code: str, report_period: str,
                       shares: float | None, ratio: float | None, holder_rank: int | None,
                       source: str, valid_from: str, valid_to: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO holding(entity_id, stock_code, report_period, shares, ratio, holder_rank, source, valid_from, valid_to)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(entity_id, stock_code, report_period) DO UPDATE SET
                 shares=COALESCE(excluded.shares, shares), ratio=COALESCE(excluded.ratio, ratio),
                 holder_rank=COALESCE(excluded.holder_rank, holder_rank), valid_to=COALESCE(excluded.valid_to, valid_to)""",
            (entity_id, stock_code, report_period, shares, ratio, holder_rank, source, valid_from, valid_to),
        )

    # ---- position ----
    def upsert_position(self, *, entity_id: int, stock_code: str, title: str,
                        title_class: str, source: str,
                        valid_from: str | None, valid_to: str | None) -> None:
        self.conn.execute(
            """INSERT INTO position(entity_id, stock_code, title, title_class, source, valid_from, valid_to)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(entity_id, stock_code, title, valid_from) DO NOTHING""",
            (entity_id, stock_code, title, title_class, source, valid_from, valid_to),
        )

    # ---- actual_controller ----
    def upsert_controller(self, *, stock_code: str, entity_id: int,
                          control_ratio: float | None, source: str,
                          valid_from: str | None, valid_to: str | None) -> None:
        self.conn.execute(
            """INSERT INTO actual_controller(stock_code, entity_id, control_ratio, source, valid_from, valid_to)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(stock_code, entity_id) DO UPDATE SET
                 control_ratio=COALESCE(excluded.control_ratio, control_ratio),
                 valid_to=COALESCE(excluded.valid_to, valid_to)""",
            (stock_code, entity_id, control_ratio, source, valid_from, valid_to),
        )

    def log_ingest(self, source: str, report_period: str | None, n_rows: int) -> None:
        self.conn.execute(
            "INSERT INTO ingest_log(source, report_period, n_rows) VALUES(?,?,?)",
            (source, report_period, n_rows),
        )

    def commit(self) -> None:
        self.conn.commit()

    # ---- gold (P4) ----
    def upsert_gold(self, *, stock_code: str, report_year: int | None,
                    party_name: str, party_entity_id: int | None = None,
                    relation_desc: str | None = None, source_url: str | None = None,
                    source_page: int | None = None) -> None:
        self.conn.execute(
            """INSERT INTO gold_related_party(stock_code, report_year, party_name, party_entity_id, relation_desc, source_url, source_page)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(stock_code, report_year, party_name) DO UPDATE SET
                 party_entity_id=COALESCE(excluded.party_entity_id, party_entity_id),
                 relation_desc=COALESCE(excluded.relation_desc, relation_desc),
                 source_url=COALESCE(excluded.source_url, source_url),
                 source_page=COALESCE(excluded.source_page, source_page)""",
            (stock_code, report_year, party_name, party_entity_id, relation_desc, source_url, source_page),
        )

    def get_gold(self, stock_code: str) -> list:
        return list(self.conn.execute(
            "SELECT * FROM gold_related_party WHERE stock_code=?", (stock_code,)).fetchall())

    # ---- event (P6) ----
    def upsert_event(self, *, event_type: str, subject_code: str | None,
                     counterparty: str | None = None, amount: float | None = None,
                     summary: str | None = None, event_date: str | None = None,
                     source_type: str = "structured", source_url: str | None = None,
                     extract_conf: str | None = None, counterparty_entity_id: int | None = None) -> None:
        self.conn.execute(
            """INSERT INTO event(event_type, event_date, subject_code, counterparty,
               counterparty_entity_id, amount, summary, source_url, source_type, extract_conf)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (event_type, event_date, subject_code, counterparty, counterparty_entity_id,
             amount, summary, source_url, source_type, extract_conf))

    def get_events(self, stock_code: str, as_of: str | None = None) -> list:
        """公司事件按日期排序(时间线)。"""
        rows = list(self.conn.execute(
            "SELECT * FROM event WHERE subject_code=? ORDER BY event_date", (stock_code,)).fetchall())
        return rows
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in ["company", "entity", "holding", "position", "actual_controller"]:
            out[t] = int(self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        out["entity_channel"] = int(
            self.conn.execute("SELECT COUNT(*) FROM entity WHERE is_channel=1").fetchone()[0])
        return out
