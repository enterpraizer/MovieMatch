# MovieMatch

## Backend skeleton

Добавлены два сервиса FastAPI:
- `apps/orchestrator/main.py`
- `apps/gateway/main.py`

Базовые endpoint'ы:
- `GET /health`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /recommendations/{mode}` (`mode`: `collaborative`, `nlp`, `mood`)

### Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Скопируй конфиг окружения:

```bash
cp .env.example .env
```

Подними локальную инфру:

```bash
docker compose up -d postgres redis
```

Применение миграций БД:

```bash
alembic upgrade head
```

Импорт сэмпла данных (MovieLens + IMDb):

```bash
python scripts/ingest_sample_data.py --ratings-limit 50000 --imdb-limit 20000
```

Запуск orchestrator:

```bash
uvicorn apps.orchestrator.main:app --host 0.0.0.0 --port 8001 --reload
```

Запуск gateway (в другом терминале):

```bash
uvicorn apps.gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

Проверка health:

```bash
curl http://localhost:8001/health
curl http://localhost:8000/health
```

Пример запроса:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@moviematch.dev","password":"demo123"}'
```

Ответ содержит `access_token` и `refresh_token`.

Обновление токена:

```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<your_refresh_token>"}'
```

Запрос рекомендаций (требуется access token):

```bash
curl -X POST http://localhost:8000/recommendations/nlp \
  -H "Authorization: Bearer <your_access_token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"space drama", "top_k": 5}'
```

По умолчанию включен dev-режим `AUTH_AUTO_CREATE_USER=true`: если пользователя с email нет, он будет создан при первом login.

## Data ingestion и E2E проверка

Скрипты:
- `/Users/nikitaradcenko/Documents/Work/CourseProject/MovieMatch/scripts/ingest_sample_data.py`
- `/Users/nikitaradcenko/Documents/Work/CourseProject/MovieMatch/scripts/verify_e2e.py`

Команда e2e-проверки:

```bash
python scripts/verify_e2e.py --gateway-url http://localhost:8000
```

Ожидаемо:
- `collaborative: ok (...)`
- `nlp: ok (...)`
- `mood: ok (...)`
- `E2E passed`

## Vertical Slice (Frontend + Backend)

Flow:
- `frontend` (React) -> `gateway` -> `orchestrator` -> `worker` -> `db/cache` -> response

Frontend files:
- `/Users/nikitaradcenko/Documents/Work/CourseProject/MovieMatch/frontend/src/App.tsx`
- `/Users/nikitaradcenko/Documents/Work/CourseProject/MovieMatch/frontend/src/main.tsx`

Запуск frontend:

```bash
cd frontend
npm install
npm run dev
```

Открой: `http://localhost:5173`

Перед запуском фронта backend должен быть поднят:

```bash
uvicorn apps.orchestrator.main:app --host 0.0.0.0 --port 8001 --reload
uvicorn apps.gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

## Observability and Resilience

Что добавлено:
- Structured JSON logs (`apps/common/observability.py`)
- Sentry integration (optional via `SENTRY_DSN`)
- Prometheus metrics endpoint: `GET /metrics` на gateway и orchestrator
- Таймауты/ретраи:
  - gateway -> orchestrator HTTP call
  - orchestrator -> worker execution
- Fallback:
  - cache fallback (in-memory if Redis недоступен)
  - recommendation fallback к collaborative mode при сбоях mode-specific обработки

Проверка метрик:

```bash
curl http://localhost:8000/metrics | head
curl http://localhost:8001/metrics | head
```

## Tests

Минимальный набор добавлен:
- Unit: `/Users/nikitaradcenko/Documents/Work/CourseProject/MovieMatch/tests/unit/test_recommender.py`
- Integration API: `/Users/nikitaradcenko/Documents/Work/CourseProject/MovieMatch/tests/integration/test_orchestrator_api.py`
- Smoke E2E: `/Users/nikitaradcenko/Documents/Work/CourseProject/MovieMatch/tests/smoke/test_e2e_gateway_flow.py`

Локальный запуск:

```bash
source .venv/bin/activate
pytest -q
```

CI:
- `/Users/nikitaradcenko/Documents/Work/CourseProject/MovieMatch/.github/workflows/ci.yml`
- job `Python checks` автоматически выполняет `pytest -q`, если папка `tests` существует.

## Database (SQLAlchemy + Alembic)

Добавлено:
- SQLAlchemy ORM модели: `/apps/common/db/models.py`
- Session/engine: `/apps/common/db/session.py`
- Alembic config: `/alembic.ini`, `/alembic/env.py`
- Первая миграция: `/alembic/versions/0001_create_initial_tables.py`

Созданные таблицы:
- `users`
- `movies`
- `user_ratings`
- `recommendation_requests`
- `recommendation_results`

## CI/CD (GitHub Actions)

В репозитории добавлены workflow:
- `.github/workflows/ci.yml` — проверки на PR и push
- `.github/workflows/cd.yml` — деплой по окружениям:
  - `develop` -> `staging`
  - `main` -> `production`

Есть и ручной запуск: `Actions -> CD -> Run workflow` с выбором `staging` или `production`.

## GitHub Secrets

Открой: `Settings -> Secrets and variables -> Actions -> New repository secret`

### Staging
- `STAGING_RENDER_DEPLOY_HOOK_URL`
- `STAGING_RAILWAY_DEPLOY_HOOK_URL`
- `STAGING_HEALTHCHECK_URL`

### Production
- `PRODUCTION_RENDER_DEPLOY_HOOK_URL`
- `PRODUCTION_RAILWAY_DEPLOY_HOOK_URL`
- `PRODUCTION_HEALTHCHECK_URL`

Для каждого окружения достаточно одного deploy hook (Render или Railway).

## Как это работает

1. Любой PR запускает `CI`.
2. Push в `develop` запускает `CD` в `staging`.
3. Push в `main` запускает `CD` в `production`.
4. После деплоя выполняется healthcheck (если URL задан).

## Дальше

Когда появится код проекта, `CI` автоматически начнёт запускать:
- Python проверки и тесты (если есть `requirements.txt`/`pyproject.toml` и папка `tests`)
- Frontend проверки (если есть `frontend/package.json`)
- Проверку Docker Compose (если есть `docker-compose.yml`)
