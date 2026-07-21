DEFAULT_GOAL := help

.PHONY: help sync test lint fmt precommit smoke http http-offline harness install-desktop build-docker build-mods build-mod-jobs build-mod-replay test-mod-replay build-mod-telemetry build-mod-stores run-shell-jobs run-shell-stores frontend-install frontend-dev frontend-build frontend-test frontend-lint snapshot-capture snapshot-push snapshot-pull snapshot-serve

name ?= eco-app
port ?= 4000
git-hash ?= $(shell git rev-parse HEAD 2>/dev/null || echo dev)

# dev-base ships Python 3.12 with a root-owned /opt/uv/python; this repo targets
# 3.13 (pyproject requires-python, product Dockerfile FROM python:3.13), so uv must
# download a managed 3.13. Point that download at a HOME-writable dir so `ward exec`
# (make -> uv) works in the non-root agent container. Unconditional on purpose: the
# image env-sets UV_PYTHON_INSTALL_DIR=/opt/uv/python, so `?=` would not override it.
export UV_PYTHON_INSTALL_DIR := $(HOME)/.cache/uv-python

help: ## Print this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "%-30s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## uv lock + uv sync with dev deps.
	uv lock
	uv sync --group dev

test: ## Run the pytest suite (tests/mcp + tests/jobs + tests/replay).
	uv run pytest

lint: ## ruff check + ruff format --check + mypy on src/ and tests/.
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy src tests

fmt: ## Apply ruff fixes and formatting in place.
	uv run ruff check --fix src tests
	uv run ruff format src tests

precommit: ## Run all pre-commit hooks against every file.
	uv run pre-commit run --all-files

smoke: ## End-to-end smoke test the MCP server via stdio.
	(printf '%s\n' \
	  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{"extensions":{"io.modelcontextprotocol/ui":{"mimeTypes":["text/html;profile=mcp-app"]}}},"clientInfo":{"name":"claude-ai","version":"0.1.0"}}}' \
	  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
	  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
	  '{"jsonrpc":"2.0","id":3,"method":"resources/read","params":{"uri":"ui://eco/status.html"}}' \
	  '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_eco_server_status","arguments":{}}}' \
	  '{"jsonrpc":"2.0","id":5,"method":"resources/read","params":{"uri":"ui://eco/economy.html"}}' \
	  '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"get_eco_economy","arguments":{}}}'; sleep 8) | uv run python -m eco_mcp_app

frontend-install: ## Install frontend deps into frontend/node_modules (pnpm).
	cd frontend && pnpm install

frontend-dev: ## Vite dev server with HMR on :5173, proxying API routes to :4000.
	cd frontend && pnpm dev

frontend-build: ## Typecheck + production-build the React SPA into frontend/dist.
	cd frontend && pnpm build

frontend-test: ## Run the frontend vitest suite.
	cd frontend && pnpm test

frontend-lint: ## ESLint over frontend/src.
	cd frontend && pnpm lint

http: ## Run the fused server (MCP + /jobs) with autoreload, eco target auto-resolved. Args - http_port=<int>.
	@BASE=$$(scripts/resolve-eco-target.sh) && \
	KEY="$${UPSTREAM_API_KEY:-$$(coily ops aws ssm get-parameter --name /eco-mcp-app/api-admin-token --with-decryption --query Parameter.Value --output text 2>/dev/null || true)}" && \
	DEBUG=1 \
	ECO_INFO_URL="$${ECO_INFO_URL:-$$BASE/info}" \
	ECO_ADMIN_BASE_URL="$${ECO_ADMIN_BASE_URL:-$$BASE}" \
	ECO_MAP_BASE_URL="$${ECO_MAP_BASE_URL:-$$BASE}" \
	UPSTREAM_URL="$${UPSTREAM_URL:-$$BASE/api/v1/skills}" \
	UPSTREAM_API_KEY="$$KEY" \
	ECO_ADMIN_TOKEN="$${ECO_ADMIN_TOKEN:-$$KEY}" \
	ECO_ADMIN_API_KEY="$${ECO_ADMIN_API_KEY:-$$KEY}" \
	uv run uvicorn eco_mcp_app.http_app:app --reload --reload-dir src --host 0.0.0.0 --port $(or $(http_port),$(port))

http-offline: ## Run the fused server against the local snapshot fixture (snapshot-serve) instead of a live eco server. Args - http_port=<int>, fixture_port=<int>.
	ECO_INFO_URL="http://localhost:$(or $(fixture_port),3101)/info" \
	UPSTREAM_API_KEY="$${UPSTREAM_API_KEY:-offline-fixture}" \
	$(MAKE) http

snapshot_dir ?= .snapshots/current
snapshot_bucket ?= s3://kai-game-backups/eco-app/snapshots

snapshot-capture: ## Capture every upstream eco-server dataset into a local snapshot dir. Args - snapshot_dir=<path>.
	@BASE=$$(scripts/resolve-eco-target.sh) && \
	KEY="$${UPSTREAM_API_KEY:-$$(aws ssm get-parameter --name /eco-mcp-app/api-admin-token --with-decryption --query Parameter.Value --output text 2>/dev/null || true)}" && \
	UPSTREAM_API_KEY="$$KEY" uv run python -m eco_snapshot capture --base-url "$$BASE" --out $(snapshot_dir)

snapshot-push: ## Tar the captured snapshot and push it to S3, timestamped plus latest. Args - snapshot_dir=<path>.
	@test -f $(snapshot_dir)/manifest.json || { echo "no snapshot at $(snapshot_dir); run snapshot-capture first" >&2; exit 1; }
	@STAMP=$$(date -u +%Y-%m-%dT%H%M%SZ) && \
	TAR=$$(mktemp -d)/snapshot.tar.gz && \
	tar -czf "$$TAR" -C $(snapshot_dir) . && \
	aws s3 cp "$$TAR" $(snapshot_bucket)/$$STAMP.tar.gz && \
	aws s3 cp $(snapshot_bucket)/$$STAMP.tar.gz $(snapshot_bucket)/latest.tar.gz && \
	rm -f "$$TAR" && \
	echo "pushed $(snapshot_bucket)/$$STAMP.tar.gz (+ latest.tar.gz)"

snapshot-pull: ## Pull a snapshot tarball from S3 into the local snapshot dir. Args - snap=<stamp|latest>, snapshot_dir=<path>.
	@TAR=$$(mktemp -d)/snapshot.tar.gz && \
	aws s3 cp $(snapshot_bucket)/$(or $(snap),latest).tar.gz "$$TAR" && \
	rm -rf $(snapshot_dir) && mkdir -p $(snapshot_dir) && \
	tar -xzf "$$TAR" -C $(snapshot_dir) && rm -f "$$TAR" && \
	echo "pulled $(snapshot_bucket)/$(or $(snap),latest).tar.gz into $(snapshot_dir)"

snapshot-serve: ## Replay the pulled snapshot as a fixture eco server on localhost. Args - fixture_port=<int>, snapshot_dir=<path>.
	uv run python -m eco_snapshot serve --dir $(snapshot_dir) --port $(or $(fixture_port),3101)

harness: ## Serve static/harness.html, the local Claude-Desktop-mimicking iframe host. Args - harness_port=<int>.
	@echo "Harness: http://localhost:$(or $(harness_port),8765)/static/harness.html"
	python3 -m http.server $(or $(harness_port),8765)

install-desktop: ## Wire eco-mcp-app into Claude Desktop's claude_desktop_config.json.
	python3 scripts/install-desktop-config.py

build-docker: ## Build the eco-app docker image locally.
	docker build --progress plain -t $(name):$(git-hash) -t $(name):latest .

build-mods: ## Restore and build every Eco mod DLL (jobs, replay, telemetry, stores) with per-project timings.
	sh scripts/mods-gate.sh build-mods

build-mod-jobs: ## Build the jobs-tracker Eco mod DLL (mods/jobs/src).
	cd mods/jobs && dotnet build src/EcoJobsTracker.csproj -c Release

build-mod-replay: ## Build the replay Eco mod DLL (mods/replay/src).
	cd mods/replay/src && dotnet build EcoReplay.csproj -c Release

test-mod-replay: ## Restore and run the replay mod C# unit tests (mods/replay/tests) with per-phase timings.
	sh scripts/mods-gate.sh test-mod-replay

build-mod-telemetry: ## Build the telemetry Eco mod DLL (mods/telemetry).
	cd mods/telemetry && dotnet build EcoTelemetry.csproj -c Release

build-mod-stores: ## Build the store-exporter Eco mod DLL (mods/stores/src).
	cd mods/stores && dotnet build src/EcoStoreExporter.csproj -c Release

run-shell-jobs: ## Run the jobs C# shell harness on :5100 (same API shape as the real Eco mod).
	cd mods/jobs && dotnet run --project shell/EcoJobsTracker.Shell.csproj

run-shell-stores: ## Run the stores C# shell harness on :5101 (same API shape as the real Eco mod).
	cd mods/stores && dotnet run --project shell/EcoStoreExporter.Shell.csproj
