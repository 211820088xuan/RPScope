-- RPScope SQLite 事实源 schema (P1 临时; PostgreSQL 就绪后迁移)
-- 对应开发指导 4.1 节。events/document/doc_chunk/gold_related_party 留待 P4/P6/P7。

CREATE TABLE IF NOT EXISTS company (
  stock_code    TEXT PRIMARY KEY,
  short_name    TEXT NOT NULL,
  full_name     TEXT,
  industry      TEXT,
  list_date     TEXT,
  market_cap    REAL,
  is_st         INTEGER DEFAULT 0,
  updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entity (
  entity_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type   TEXT NOT NULL,          -- person | org | fund | channel | unknown
  canonical_name TEXT NOT NULL,         -- 归一化匹配键
  display_name  TEXT,                   -- 原始展示名
  raw_names     TEXT,                    -- JSON array of 原始写法
  is_channel    INTEGER DEFAULT 0,
  credit_code   TEXT,
  disambig_note TEXT,
  confidence    TEXT,                    -- high | medium | low
  UNIQUE (entity_type, canonical_name)
);

CREATE TABLE IF NOT EXISTS holding (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id     INTEGER REFERENCES entity(entity_id),
  stock_code    TEXT REFERENCES company(stock_code),
  report_period TEXT NOT NULL,
  shares        REAL,
  ratio         REAL,                   -- 持股比例 % (批量接口无, NULL; 个股接口补)
  holder_rank   INTEGER,
  source        TEXT NOT NULL,
  valid_from    TEXT NOT NULL,
  valid_to      TEXT,
  UNIQUE (entity_id, stock_code, report_period)
);
CREATE INDEX IF NOT EXISTS idx_holding_stock ON holding(stock_code, report_period);
CREATE INDEX IF NOT EXISTS idx_holding_entity ON holding(entity_id);

CREATE TABLE IF NOT EXISTS position (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id     INTEGER REFERENCES entity(entity_id),
  stock_code    TEXT REFERENCES company(stock_code),
  title         TEXT NOT NULL,
  title_class   TEXT NOT NULL,          -- director | supervisor | senior_mgmt | independent_director | other
  source        TEXT NOT NULL,
  valid_from    TEXT,
  valid_to      TEXT,
  UNIQUE (entity_id, stock_code, title, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_position_entity ON position(entity_id);
CREATE INDEX IF NOT EXISTS idx_position_stock ON position(stock_code);

CREATE TABLE IF NOT EXISTS actual_controller (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_code    TEXT REFERENCES company(stock_code),
  entity_id     INTEGER REFERENCES entity(entity_id),
  control_ratio REAL,
  source        TEXT,
  valid_from    TEXT,
  valid_to      TEXT,
  UNIQUE (stock_code, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_controller_stock ON actual_controller(stock_code);

-- 元数据: 记录每次 ingest 的来源接口与行数, 供可回溯
CREATE TABLE IF NOT EXISTS ingest_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source        TEXT NOT NULL,
  report_period TEXT,
  n_rows        INTEGER,
  ingested_at   TEXT DEFAULT (datetime('now'))
);

-- 金标准(P4): 年报披露的关联方清单, 作 P5 评测外部基准
CREATE TABLE IF NOT EXISTS gold_related_party (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_code    TEXT NOT NULL,
  report_year   INT,
  party_name    TEXT NOT NULL,           -- 年报披露的关联方名称(原文)
  party_entity_id INTEGER,               -- 映射到 entity 表(可空=未映射)
  relation_desc TEXT,                    -- 年报描述的关系
  source_url    TEXT,
  source_page   INT,                     -- 来源页码
  ingested_at   TEXT DEFAULT (datetime('now')),
  UNIQUE (stock_code, report_year, party_name)
);
CREATE INDEX IF NOT EXISTS idx_gold_stock ON gold_related_party(stock_code);

-- 事件(P6): 担保/诉讼/质押/关联交易等风险事件
CREATE TABLE IF NOT EXISTS event (
  event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type    TEXT NOT NULL,           -- guarantee | lawsuit | pledge | related_txn | penalty | other
  event_date    TEXT,
  subject_code  TEXT,                    -- 主体公司股票代码
  counterparty  TEXT,                     -- 交易对手原文(质押:出质人/质权人; 担保/诉讼:聚合无对手)
  counterparty_entity_id INTEGER,        -- 消歧后实体
  amount        REAL,
  summary       TEXT,
  source_url    TEXT,
  source_type   TEXT NOT NULL,            -- structured | llm_extracted
  extract_conf  TEXT,                     -- LLM 抽取置信度
  ingested_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_event_subject ON event(subject_code);
CREATE INDEX IF NOT EXISTS idx_event_type ON event(event_type);

