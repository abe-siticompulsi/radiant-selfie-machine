# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY web ./web
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" RSM_WEB=/app/web

FROM base AS servizio
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salute', timeout=3)"
# --no-access-log: il percorso della pagina contiene il gettone.
CMD ["uvicorn", "--factory", "rsm.principale:costruisci", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM base AS prova
COPY tests ./tests
RUN uv sync --frozen
CMD ["pytest", "-m", "reale", "-rs", "tests/reale"]
