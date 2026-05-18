FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app/apps/api:/app/apps/worker

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir ".[dev]"

COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker

CMD ["celery", "-A", "worker.main.celery_app", "worker", "--loglevel=INFO"]
