DEFAULT_GOAL := help

.PHONY: help sync test lint fmt precommit smoke http harness install-desktop build-docker build-mod-jobs build-mod-replay build-mod-telemetry run-shell-jobs

name ?= eco-app
port ?= 4000
git-hash ?= $(shell git rev-parse HEAD 2>/dev/null || echo dev)

help: ## Print this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "%-30s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## uv lock + uv sync with dev deps.
	uv lock
	uv sync --group dev

test: ## Run the pytest suite (tests/mcp + tests/jobs).
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

http: ## Run the fused server (MCP + /jobs) with autoreload. Args - http_port=<int>.
	DEBUG=1 uv run uvicorn eco_mcp_app.http_app:app --reload --reload-dir src --host 0.0.0.0 --port $(or $(http_port),$(port))

harness: ## Serve static/harness.html, the local Claude-Desktop-mimicking iframe host. Args - harness_port=<int>.
	@echo "Harness: http://localhost:$(or $(harness_port),8765)/static/harness.html"
	python3 -m http.server $(or $(harness_port),8765)

install-desktop: ## Wire eco-mcp-app into Claude Desktop's claude_desktop_config.json.
	python3 scripts/install-desktop-config.py

build-docker: ## Build the eco-app docker image locally.
	docker build --progress plain -t $(name):$(git-hash) -t $(name):latest .

build-mod-jobs: ## Build the jobs-tracker Eco mod DLL (mods/jobs/src).
	cd mods/jobs && dotnet build src/EcoJobsTracker.csproj -c Release

build-mod-replay: ## Build the replay Eco mod DLL (mods/replay/src).
	cd mods/replay/src && dotnet build EcoReplay.csproj -c Release

build-mod-telemetry: ## Build the telemetry Eco mod DLL (mods/telemetry).
	cd mods/telemetry && dotnet build EcoTelemetry.csproj -c Release

run-shell-jobs: ## Run the jobs C# shell harness on :5100 (same API shape as the real Eco mod).
	cd mods/jobs && dotnet run --project shell/EcoJobsTracker.Shell.csproj
