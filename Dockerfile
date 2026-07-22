ARG AOS_REGISTRY=forgejo.coilysiren.me/coilyco-flight-deck/agentic-os
ARG AOS_TAG=v0.255.0

FROM ${AOS_REGISTRY}:lang-node-${AOS_TAG} AS frontend

WORKDIR /frontend

RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml /frontend/
RUN pnpm install --frozen-lockfile

COPY frontend/ /frontend/
RUN pnpm build

FROM ${AOS_REGISTRY}:core-${AOS_TAG} AS runtime

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project

COPY . /app
RUN uv sync --frozen --no-dev

COPY --from=frontend /frontend/dist /app/frontend/dist

ENV PORT=4000
EXPOSE $PORT

CMD ["sh", "-c", ".venv/bin/uvicorn eco_mcp_app.http_app:app --host 0.0.0.0 --port $PORT"]
