# MovieMatch

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
