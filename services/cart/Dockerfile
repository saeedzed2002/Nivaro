ARG PYTHON_IMAGE=python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5
FROM ${PYTHON_IMAGE} AS dependencies
WORKDIR /workspace/services/cart
ARG PYTHON_INDEX_URL=https://pypi.org/simple
ENV UV_HTTP_TIMEOUT=20 UV_HTTP_RETRIES=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN --mount=type=cache,target=/root/.cache pip install --disable-pip-version-check --timeout 20 --retries 1 uv==0.13.5
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt && uv venv /app/.venv && uv pip sync --python /app/.venv/bin/python --require-hashes --default-index "$PYTHON_INDEX_URL" /tmp/requirements.txt
COPY src ./src
RUN --mount=type=cache,target=/root/.cache uv pip install --python /app/.venv/bin/python --no-deps --default-index "$PYTHON_INDEX_URL" .

FROM dependencies AS test
RUN --mount=type=cache,target=/root/.cache uv export --frozen --no-emit-project -o /tmp/requirements-test.txt && uv pip install --python /app/.venv/bin/python --require-hashes --default-index "$PYTHON_INDEX_URL" -r /tmp/requirements-test.txt
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
RUN groupadd --gid 10003 cart && useradd --uid 10003 --gid cart --no-create-home cart
COPY --from=dependencies --chown=cart:cart /app /app
COPY --chown=cart:cart alembic.ini ./
COPY --chown=cart:cart migrations ./migrations
USER cart
EXPOSE 8000
CMD ["uvicorn", "nivaro_cart.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
