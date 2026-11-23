SHELL := /bin/bash
.DEFAULT_GOAL := help

DATA_DIR ?= data
INTERVAL ?= 7200
JITTER ?= 0.1
PROXY ?=
PORT ?= 8501
PY := uv run
WEB := web

.PHONY: help install lock once daemon start stop status logs export stats datasets dashboard \
	web-install web-check test check fmt typecheck clean

help:
	@echo "make install          python + bun dependencies"
	@echo "make once             crawl all datasets once"
	@echo "make daemon           crawl in the foreground (Ctrl-C to stop)"
	@echo "make start            crawl in the background (logs to $(DATA_DIR)/crawler.log)"
	@echo "make stop             stop the background crawler"
	@echo "make status           check the background crawler"
	@echo "make logs             follow the background crawler log"
	@echo "make dashboard        open the Bun/ECharts dashboard on :$(PORT)"
	@echo "make export           re-export the latest snapshot to $(DATA_DIR)/export"
	@echo "make stats            last run and active record counts"
	@echo "make datasets         list all datasets"
	@echo "make test             python tests"
	@echo "make fmt              uv format + prettier"
	@echo "make typecheck        uv tool run ty check + bun tsc"
	@echo "make check            format check + typecheck + tests"
	@echo ""
	@echo "Optional: make once PROXY=http://127.0.0.1:7890 INTERVAL=3600"

install:
	uv sync
	cd $(WEB) && bun install

lock:
	uv lock
	cd $(WEB) && bun install

once:
	$(PY) aa-crawler --data-dir "$(DATA_DIR)" $(if $(PROXY),--proxy "$(PROXY)") once

daemon:
	$(PY) aa-crawler --data-dir "$(DATA_DIR)" $(if $(PROXY),--proxy "$(PROXY)") daemon --interval $(INTERVAL) --jitter $(JITTER)

start: install
	@mkdir -p "$(DATA_DIR)"
	@if [ -f "$(DATA_DIR)/crawler.pid" ] && kill -0 "$$(cat "$(DATA_DIR)/crawler.pid")" 2>/dev/null; then \
		echo "already running (pid $$(cat "$(DATA_DIR)/crawler.pid"))"; exit 1; \
	fi
	@nohup .venv/bin/aa-crawler --data-dir "$(DATA_DIR)" $(if $(PROXY),--proxy "$(PROXY)") daemon --interval $(INTERVAL) --jitter $(JITTER) \
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
	$(PY) aa-crawler --data-dir "$(DATA_DIR)" export

stats:
	$(PY) aa-crawler --data-dir "$(DATA_DIR)" stats

datasets:
	$(PY) aa-crawler datasets

web-install:
	cd $(WEB) && bun install --frozen-lockfile

dashboard: web-install
	cd $(WEB) && AA_DB="$(abspath $(DATA_DIR)/aa.db)" AA_MANIFEST="$(abspath $(DATA_DIR)/datasets.json)" PORT=$(PORT) bun run start

web-check:
	cd $(WEB) && bun run check
	cd $(WEB) && bun run format:check

test:
	$(PY) pytest

fmt:
	uv format
	cd $(WEB) && bun run format

typecheck:
	uv tool run ty check
	cd $(WEB) && bun run check

check:
	uv format --check
	uv tool run ty check
	$(PY) pytest
	cd $(WEB) && bun run check
	cd $(WEB) && bun run format:check

clean:
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
