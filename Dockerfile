FROM mcr.microsoft.com/playwright/python:v1.47.0-noble

WORKDIR /srv/app

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN groupadd app \
    && useradd --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /srv/app/data/cookies \
    && chown -R app:app /srv/app

USER app

ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
