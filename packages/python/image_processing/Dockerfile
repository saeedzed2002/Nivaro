ARG PYTHON_IMAGE=python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5
FROM ${PYTHON_IMAGE} AS test
WORKDIR /app
ARG PYTHON_INDEX_URL=https://pypi.org/simple
ENV UV_HTTP_TIMEOUT=20 UV_HTTP_RETRIES=0 UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache pip install --disable-pip-version-check --timeout 20 --retries 0 uv==0.13.5
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache uv export --frozen --no-emit-project -o /tmp/requirements.txt && uv venv && uv pip sync --python .venv/bin/python --require-hashes --default-index "$PYTHON_INDEX_URL" /tmp/requirements.txt
COPY src ./src
RUN --mount=type=cache,target=/root/.cache uv pip install --python .venv/bin/python --no-deps --default-index "$PYTHON_INDEX_URL" .
COPY tests ./tests
ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "ruff check . && ruff format --check . && mypy src && pytest -q"]
