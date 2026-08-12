FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv \
    && groupadd --system roxie \
    && useradd --system --gid roxie --create-home roxie

COPY --chown=roxie:roxie pyproject.toml uv.lock README.md .python-version ./

RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=roxie:roxie app ./app
COPY --chown=roxie:roxie myskills ./myskills

RUN mkdir -p /app/.nacos/logs /app/.nacos/cache \
    && chown -R roxie:roxie /app/.nacos

USER roxie

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)" || exit 1

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
