FROM python:3.13-slim

WORKDIR /app

# psycopg2-binary needs libpq at runtime; build-essential covers any source builds on slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

EXPOSE 8000

# --proxy-headers/--forwarded-allow-ips: run behind Render's load balancer, so the real client
# address (used in logs and rate-limit fallbacks) comes from X-Forwarded-For.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
