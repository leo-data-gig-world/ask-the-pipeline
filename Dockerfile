# Slack bot image. The serving database is built at image build time from the
# public pipeline, so each daily rebuild ships fresh data with no warehouse credentials.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home bot
WORKDIR /app

COPY requirements.txt requirements-warehouse.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m venv /opt/dbt && /opt/dbt/bin/pip install --no-cache-dir -r requirements-warehouse.txt

COPY agent ./agent
COPY scripts ./scripts
COPY context ./context
RUN DBT_BIN=/opt/dbt/bin/dbt python scripts/build_warehouse.py && chown -R bot /app

USER bot
# No secrets in the image: LLM_API_KEY, SLACK_BOT_TOKEN and SLACK_APP_TOKEN are injected at runtime.
CMD ["python", "-m", "agent.slack_app"]
