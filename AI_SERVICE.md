# AI Service

AI processing is asynchronous. Django owns the business data and stores work in `core.AiTask`.
The AI worker runs as a separate process or on a separate server and communicates only through
the internal HTTP API under `/internal/ai/`.

## Flow

1. Django creates an `AiTask` when a motivation letter, interview video, scholar video, or interview transcript needs AI work.
2. The AI worker calls `POST /internal/ai/tasks/claim/` and receives one task with a lease.
3. The worker sends heartbeat requests while long tasks are running.
4. The worker posts either `complete` with a structured result or `fail` with an error.
5. Django validates and applies the result to the existing domain models.

## Local Docker

```powershell
docker compose up -d --build
```

The main compose starts only:

- `web`: Django and non-AI background workers.
- `db`: PostgreSQL.

Create `.env.ai.local` from `.env.ai.example`, then start the AI worker separately:

```powershell
Copy-Item .env.ai.example .env.ai.local
# edit .env.ai.local
docker compose -f docker-compose.ai.yml up -d --build
```

Both compose files use the same Docker network, `putevka_app`, so the local AI worker can reach
Django at `http://web:8000`.

Stop only the AI worker:

```powershell
docker compose -f docker-compose.ai.yml down
```

## Remote Server

Build and run `ai_service/Dockerfile` on the AI server. The worker needs:

- `AI_SERVICE_TOKEN`: same secret as Django.
- `AI_DJANGO_BASE_URL`: public or private URL of Django, for example `https://app.example.org`.
- `OPENAI_API_KEY` or `GPT_TOKEN`: OpenAI token, stored on the AI server.
- `TELEGRAM_SOCKS5_PROXY`: optional proxy reused for OpenAI HTTP traffic.

Example:

```powershell
docker build -f ai_service/Dockerfile -t putevka-ai-worker .
docker run --env-file .env.ai.local putevka-ai-worker
```

## GitHub Actions Deploy

The workflow `.github/workflows/deploy-ai-service.yml` deploys only the AI service files to a
separate server and runs:

```powershell
docker compose --env-file .env.ai.local -f docker-compose.ai.yml up -d --build --remove-orphans
```

Required repository secrets:

- `AI_DEPLOY_HOST`: AI server host or IP.
- `AI_DEPLOY_USER`: SSH user on the AI server.
- `AI_DEPLOY_SSH_KEY`: private SSH key with access to that user.
- `AI_DEPLOY_PATH`: target directory on the AI server, for example `/opt/putevka-ai`.
- `AI_DEPLOY_ENV_FILE`: full `.env.ai.local` contents.

The workflow runs manually from GitHub Actions or automatically on pushes to branches ending
with `--ai` when AI service files change.

`entrypoint.sh` no longer starts `Shadows/gpt_reviewer.py`, `Shadows/gpt_transcriber.py`,
`Shadows/gpt_transcriber_video.py`, or `Shadows/gpt_fill_form.py`.

## Backfill

After deploying migrations, enqueue existing pending objects:

```powershell
python manage.py enqueue_ai_tasks
```
