FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /srv/app

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir -e .

CMD ["region-price-monitor", "healthcheck"]
