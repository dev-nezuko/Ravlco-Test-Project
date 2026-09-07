FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY contracts ./contracts
COPY orchestration ./orchestration
RUN pip install ".[dev]"

COPY . .
RUN useradd --create-home app && chown -R app /app
USER app

# Demo run by default; override the command for tests, queries or `dagster dev`.
CMD ["python", "run_pipeline.py"]
