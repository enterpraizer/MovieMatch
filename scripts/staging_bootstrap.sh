#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
fi

# Bring up full staging stack

docker compose -f docker-compose.staging.yml up -d --build

# Run migrations in orchestrator container

docker compose -f docker-compose.staging.yml exec -T orchestrator alembic upgrade head

# Load small sample dataset for smoke checks (optional)
if docker compose -f docker-compose.staging.yml exec -T orchestrator test -f data/raw/ml-25m/movies.csv; then
  docker compose -f docker-compose.staging.yml exec -T orchestrator \
    python scripts/ingest_sample_data.py --ratings-limit 5000 --imdb-limit 2000
else
  echo "Sample datasets are not present inside container image, skipping ingestion."
fi

# Smoke check

python scripts/smoke_check_staging.py --base-url http://localhost:8000

echo "Staging stack is healthy"
