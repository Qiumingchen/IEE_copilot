FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app/apps/api:/app/apps/worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends mafft \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir ".[dev]"

COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker
COPY scripts /app/scripts
COPY data /app/data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "apps/api"]
