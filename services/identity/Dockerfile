ARG PYTHON_IMAGE=python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5
FROM ${PYTHON_IMAGE} AS dependencies
WORKDIR /app
ARG PYTHON_INDEX_URL=https://pypi.org/simple
ENV UV_HTTP_TIMEOUT=20 UV_HTTP_RETRIES=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN --mount=type=cache,target=/root/.cache pip install --disable-pip-version-check --timeout 20 --retries 1 uv==0.13.5
COPY pyproject.toml uv.lock ./
# Preserve lock versions/hashes while using an index reachable from the builder.
# The local lock records regional mirror URLs, which external CI cannot reach.
RUN --mount=type=cache,target=/root/.cache uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt && uv venv && uv pip sync --python .venv/bin/python --require-hashes --default-index "$PYTHON_INDEX_URL" /tmp/requirements.txt
COPY src ./src
RUN --mount=type=cache,target=/root/.cache uv pip install --python .venv/bin/python --no-deps --default-index "$PYTHON_INDEX_URL" .

FROM dependencies AS test
RUN --mount=type=cache,target=/root/.cache uv export --frozen --no-emit-project -o /tmp/requirements-test.txt && uv pip install --python .venv/bin/python --require-hashes --default-index "$PYTHON_INDEX_URL" -r /tmp/requirements-test.txt
COPY alembic.ini ./
COPY migrations ./migrations
COPY tests ./tests
ENV PATH="/app/.venv/bin:$PATH"

FROM ${PYTHON_IMAGE} AS release
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10002 identity && useradd --uid 10002 --gid identity --no-create-home identity
COPY --from=dependencies --chown=identity:identity /app /app
COPY --chown=identity:identity alembic.ini ./
COPY --chown=identity:identity migrations ./migrations
USER identity
EXPOSE 8000
CMD ["uvicorn", "nivaro_identity.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
