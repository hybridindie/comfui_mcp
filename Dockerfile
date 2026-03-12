FROM python:3.12-slim

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

RUN pip install --no-cache-dir uv

COPY --chown=app:app pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY --chown=app:app src/ ./src/

USER app

ENV PYTHONPATH=/app

ENTRYPOINT ["uv", "run", "comfyui-mcp"]
