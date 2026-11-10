ARG PYTHON_IMAGE=python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5
FROM ${PYTHON_IMAGE} AS dependencies
WORKDIR /workspace/services/identity
ARG PYTHON_INDEX_URL=https://pypi.org/simple
ENV UV_HTTP_TIMEOUT=20 UV_HTTP_RETRIES=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN --mount=type=cache,target=/root/.cache pip install --disable-pip-version-check --timeout 20 --retries 1 uv==0.13.5
COPY pyproject.toml uv.lock ./
COPY --from=image-processing / /workspace/packages/python/image_processing/
RUN --mount=type=cache,target=/root/.cache uv export --frozen --no-dev --no-emit-project --no-emit-package nivaro-image-processing -o /tmp/requirements.txt && uv venv /app/.venv && uv pip sync --python /app/.venv/bin/python --require-hashes --default-index "$PYTHON_INDEX_URL" /tmp/requirements.txt && uv pip install --python /app/.venv/bin/python --no-deps --default-index "$PYTHON_INDEX_URL" /workspace/packages/python/image_processing
COPY src ./src
RUN --mount=type=cache,target=/root/.cache uv pip install --python /app/.venv/bin/python --no-deps --default-index "$PYTHON_INDEX_URL" .

FROM dependencies AS test
RUN --mount=type=cache,target=/root/.cache uv export --frozen --no-emit-project --no-emit-package nivaro-image-processing -o /tmp/requirements-test.txt && uv pip install --python /app/.venv/bin/python --require-hashes --default-index "$PYTHON_INDEX_URL" -r /tmp/requirements-test.txt
WORKDIR /app
COPY src ./src
COPY pyproject.toml ./
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
