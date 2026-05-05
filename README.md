# MovieMatch

AI-powered movie recommendation system combining three independent ML approaches in a single web application.

![CI](https://img.shields.io/badge/CI-passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-80%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.12-blue)
![TypeScript](https://img.shields.io/badge/typescript-5.7-blue)

## Features

Three ways to get personalized recommendations:

- **By Ratings** — Collaborative filtering via a Two-Tower Neural Network trained on MovieLens. User rates movies, the model matches them against an item embedding catalog using cosine similarity.
- **By Description** — Semantic search over movie plots using `sentence-transformers/all-MiniLM-L6-v2` (384-dim) + pgvector HNSW index, combined with PostgreSQL full-text search via Reciprocal Rank Fusion.
- **By Mood** — Emotion detection from a selfie via a ViT ONNX model. Detected emotion maps to genre preferences (e.g., "happy" → Comedy/Adventure).

## Tech Stack

| Layer       | Technology                                                   |
|-------------|--------------------------------------------------------------|
| Frontend    | Next.js 14, TypeScript 5, Tailwind CSS v4, Zustand, TanStack Query, Framer Motion, Playwright |
| Backend     | FastAPI, Pydantic v2, asyncpg, Alembic, Redis, Celery, python-jose, bcrypt |
| Database    | PostgreSQL 16 + pgvector (HNSW) + pg_trgm                    |
| ML — RecSys | PyTorch Lightning (Two-Tower), MLflow for model registry     |
| ML — NLP    | sentence-transformers, pgvector similarity, RRF hybrid search |
| ML — CV     | ONNX Runtime (ViT emotion model), OpenCV Haar face detection  |
| Infra       | Docker Compose (dev), Kubernetes + Traefik (prod), ArgoCD CD  |
| Observability | Prometheus metrics, structured JSON logs (structlog)       |

## Quick Start (5 minutes)

**Prerequisites:** Docker Desktop, Python 3.12, Node.js 20, `uv`, `pnpm`.

```bash
# 1. Clone + env
git clone <repo-url> moviematch && cd moviematch
cp .env.example .env
# Edit .env: generate SECRET_KEY with `openssl rand -hex 32`, get TMDB_API_KEY from themoviedb.org/settings/api

# 2. Infrastructure
docker compose up -d postgres redis

# 3. Backend setup
cd backend
uv sync --extra dev
POSTGRES_URL="postgresql+asyncpg://moviematch:changeme@localhost:5432/moviematch" \
  uv run alembic upgrade head

# 4. Import test dataset (MovieLens files expected at data/raw/ml-25m/)
POSTGRES_URL="postgresql+asyncpg://moviematch:changeme@localhost:5432/moviematch" \
  uv run python scripts/data/import_movielens.py --limit 1000 --ratings-limit 50000

# 5. Index NLP embeddings
cd ../ml/nlp
POSTGRES_URL="postgresql://moviematch:changeme@localhost:5432/moviematch" \
  uv run python indexer.py

# 6. Download CV emotion model
cd ../cv
uv run python download_model.py

# 7. Start services (each in a separate terminal)
cd ../nlp    && POSTGRES_URL="postgresql://moviematch:changeme@localhost:5432/moviematch" uv run uvicorn service:app --port 8002
cd ../cv     && uv run uvicorn service:app --port 8003
cd ../recsys && POSTGRES_URL="postgresql://moviematch:changeme@localhost:5432/moviematch" MLFLOW_TRACKING_URI=./mlruns uv run uvicorn service:app --port 8001
cd ../../backend && POSTGRES_URL="postgresql+asyncpg://..." REDIS_URL=... SECRET_KEY=... TMDB_API_KEY=... uv run uvicorn main:app --port 8000

# 8. Frontend
cd ../frontend
pnpm install
pnpm generate-types   # run while backend is up
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm dev

# 9. Open http://localhost:3000
```

## Project Structure

```
moviematch/
├── backend/                   # FastAPI app (port 8000)
│   ├── routers/               # auth, movies, ratings, recommendations, health
│   ├── services/              # ML service clients + recommendation logic
│   ├── workers/               # Celery tasks (embedding refresh, analytics)
│   ├── db/                    # asyncpg pool + Alembic migrations
│   ├── middleware/            # rate limit + request logging
│   └── tests/                 # pytest suite, testcontainers integration
├── frontend/                  # Next.js 14 (port 3000)
│   ├── src/app/               # App Router pages (auth, movies, main tabs)
│   ├── src/components/        # UI primitives + feature components
│   ├── src/store/             # Zustand stores (ratings, UI)
│   └── tests/e2e/             # Playwright specs
├── ml/
│   ├── recsys/                # Two-Tower RecSys (port 8001) + training
│   ├── nlp/                   # sentence-transformers search (port 8002)
│   └── cv/                    # Emotion ONNX inference (port 8003)
├── k8s/                       # Deployments, HPA, IngressRoute, secrets template
├── .github/workflows/         # ci.yml (lint/test/docker), deploy.yml (ArgoCD)
├── scripts/
│   ├── data/                  # MovieLens import
│   ├── sql/                   # Postgres init (extensions)
│   └── monitoring/            # Service health CLI
├── data/raw/ml-25m/           # MovieLens 25M dataset (not committed)
└── docker-compose.yml
```

## Development

**Testing**

```bash
# Backend unit + integration (real postgres+redis required)
cd backend && uv run pytest tests/ -v --cov=.

# Frontend component tests
cd frontend && pnpm test

# Frontend E2E (requires all services running)
cd frontend && pnpm playwright test
```

**Linting & type-checking**

```bash
cd backend && uv run ruff check . && uv run mypy .
cd frontend && pnpm type-check && pnpm lint
```

**Training the RecSys model**

```bash
cd ml/recsys
POSTGRES_URL=... MLFLOW_TRACKING_URI=./mlruns \
  uv run python train.py --epochs 20 --batch-size 1024 --temperature 0.15

# Full-catalog evaluation
uv run python evaluate.py

# Baselines for comparison
uv run python baselines.py popularity
uv run python baselines.py als
```

## Architecture Overview

Microservices design with three independent ML workloads, all orchestrated via the FastAPI backend:

```
┌──────────┐       ┌─────────────┐
│ Frontend │ ─────▶│  Backend    │
│ Next.js  │       │  FastAPI    │
│  :3000   │       │   :8000     │──┬──▶ PostgreSQL (pgvector)
└──────────┘       └─────────────┘  │    Redis (cache + Celery broker)
                          │         │
                          ├────────▶│  NLP service :8002  (semantic + hybrid RRF)
                          ├────────▶│  CV service  :8003  (emotion ONNX)
                          └────────▶│  RecSys     :8001  (Two-Tower + MLflow)
                                    │
                                    └── Celery worker + beat
                                        (embedding refresh, analytics)
```

Each ML service has its own Dockerfile, Python environment, and scaling profile:
- **NLP** — CPU, loads a 90 MB sentence-transformer on startup (~30 s warmup)
- **CV** — CPU, stateless, ViT emotion model (~330 MB)
- **RecSys** — CPU/GPU, loads trained Two-Tower from MLflow, precomputes item catalog

Observability: Prometheus metrics on backend at `/metrics` (request counts, latency histograms, ML service availability gauges, auth events). Structured JSON logs via structlog with `X-Request-ID` propagation.

## Security and Privacy

- **Photos** sent to `/v1/recommendations/emotion` are read into RAM only, never written to disk, never logged (no filename, no size, no content). They are deleted from memory immediately after ONNX inference completes. Only the emotion label and confidence are retained transiently. Complies with GDPR Art. 9 (biometric data).
- **Passwords** hashed with bcrypt (12 rounds). Login endpoint calls bcrypt on every request — including for non-existent users — to prevent timing-attack user enumeration.
- **JWT** with `access` / `refresh` tokens, `jti` claim. Refresh tokens rotated on use; old refresh token added to Redis blacklist. Logout blacklists the provided refresh token.
- **Rate limiting** via Redis sliding-window — per-IP for unauthenticated, per-user for authenticated. Fail-open if Redis is down.
- **Secrets** never committed. `k8s/secrets/secrets.yaml.example` is a template; real secrets created via `kubectl create secret`.
- **Images** run as non-root UID 1001, `readOnlyRootFilesystem: true`, capabilities dropped.

## Full Documentation

See [`docs/superpowers/plans/2026-04-17-recsys-v3-plan.md`](docs/superpowers/plans/2026-04-17-recsys-v3-plan.md) for the RecSys improvement plan and [`docs/superpowers/plans/2026-04-17-results.md`](docs/superpowers/plans/2026-04-17-results.md) for model evaluation results (baselines vs. Two-Tower).

## License

MIT
