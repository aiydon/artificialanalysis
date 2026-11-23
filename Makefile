SHELL := /bin/bash
.DEFAULT_GOAL := help

DATA_DIR ?= data
INTERVAL ?= 21600
JITTER ?= 0.1
PROXY ?=
PY := uv run

.PHONY: help install lock once daemon start stop status logs export stats datasets test lint fmt clean

help:
	@echo "make install          install dependencies (uv sync)"
	@echo "make once             crawl all datasets once"
	@echo "make daemon           crawl in the foreground (Ctrl-C to stop)"
	@echo "make start            crawl in the background (nohup, logs to $(DATA_DIR)/crawler.log)"
	@echo "make stop             stop the background crawler"
	@echo "make status           check the background crawler"
	@echo "make logs             follow the background crawler log"
	@echo "make export           re-export the latest snapshot to $(DATA_DIR)/export"
	@echo "make stats            show last run and latest record counts"
	@echo "make test             run unit tests"
	@echo "make lint fmt         check / auto-format with ruff"
	@echo ""
	@echo "Optional: make once PROXY=http://127.0.0.1:7890 INTERVAL=3600"

install:
	uv sync

lock:
	uv lock

once:
	$(PY) aa-crawler once --data-dir "$(DATA_DIR)" $(if $(PROXY),--proxy "$(PROXY)")

daemon:
	$(PY) aa-crawler daemon --interval $(INTERVAL) --jitter $(JITTER) --data-dir "$(DATA_DIR)" $(if $(PROXY),--proxy "$(PROXY)")

start: install
	@mkdir -p "$(DATA_DIR)"
	@if [ -f "$(DATA_DIR)/crawler.pid" ] && kill -0 "$$(cat "$(DATA_DIR)/crawler.pid")" 2>/dev/null; then \
		echo "already running (pid $$(cat "$(DATA_DIR)/crawler.pid"))"; exit 1; \
	fi
	@nohup .venv/bin/aa-crawler daemon --interval $(INTERVAL) --jitter $(JITTER) --data-dir "$(DATA_DIR)" $(if $(PROXY),--proxy "$(PROXY)") \
		>> "$(DATA_DIR)/crawler.log" 2>&1 & echo $$! > "$(DATA_DIR)/crawler.pid"
	@echo "started pid $$(cat "$(DATA_DIR)/crawler.pid"); log: $(DATA_DIR)/crawler.log"

stop:
	@if [ -f "$(DATA_DIR)/crawler.pid" ] && kill -0 "$$(cat "$(DATA_DIR)/crawler.pid")" 2>/dev/null; then \
		kill "$$(cat "$(DATA_DIR)/crawler.pid")" && rm -f "$(DATA_DIR)/crawler.pid" && echo "stopped"; \
	else \
		rm -f "$(DATA_DIR)/crawler.pid"; echo "not running"; \
	fi

status:
	@if [ -f "$(DATA_DIR)/crawler.pid" ] && kill -0 "$$(cat "$(DATA_DIR)/crawler.pid")" 2>/dev/null; then \
		echo "running (pid $$(cat "$(DATA_DIR)/crawler.pid"))"; \
	else \
		echo "stopped"; \
	fi

logs:
	@tail -n 50 -F "$(DATA_DIR)/crawler.log"

export:
	$(PY) aa-crawler export --data-dir "$(DATA_DIR)"

stats:
	$(PY) aa-crawler stats --data-dir "$(DATA_DIR)"

datasets:
	$(PY) aa-crawler datasets

test:
	$(PY) pytest

lint:
	$(PY) ruff check .
	$(PY) ruff format --check .

fmt:
	$(PY) ruff check --fix .
	$(PY) ruff format .

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
