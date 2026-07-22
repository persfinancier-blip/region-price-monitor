FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir .

CMD ["python", "-m", "app.cli", "healthcheck"]
