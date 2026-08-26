# RPScope Makefile - P0 用 SQLite，P1 起换 Postgres+Neo4j
PY ?= py
PIP := $(PY) -m pip

.PHONY: install check probe ingest build-graph stats probe-analyze clean

install:
	$(PIP) install -e ".[dev]"

check:
	ruff check src tests scripts
	mypy src --ignore-missing-imports || true
	pytest -q

# P0 - 数据探针
probe:
	$(PY) scripts/probe.py

probe-analyze:
	$(PY) scripts/analyze_probe.py

# P1 起
ingest:
	$(PY) scripts/ingest.py

build-graph:
	$(PY) scripts/rebuild_graph.py

stats:
	$(PY) scripts/graph_stats.py

clean:
	rm -rf .cache *.db
