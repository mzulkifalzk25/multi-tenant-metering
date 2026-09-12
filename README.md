# Async Document Pipeline

Production-grade async document processing pipeline with idempotent, non-destructive job orchestration.

Documents (PDF, image, video) are ingested via HTTP or Redis pub/sub, fanned out into per-page/per-frame **work units**, and processed through Celery with exponential-backoff retries. Every processing attempt is recorded as an immutable **execution generation**, so retries never destroy history and every step is safe to re-run.

## Key concepts

- **Job** -- a single uploaded document awaiting processing.
- **Execution** -- one attempt at a job. Retries create a *new* execution generation rather than mutating the last one, so every attempt (successful or not) stays inspectable forever.
- **Work unit** -- the smallest unit of fan-out work: one per PDF page, one per sampled video frame, one for an image.
- **Idempotency** -- work units are keyed by a deterministic id (`execution_id:unit_type:unit_number`), so re-expanding or reprocessing the same execution generation twice never duplicates work.
- **Status** -- a single mutable pointer per execution (`ingested -> expanded -> executing -> completed|failed`) answering "where is this execution right now" without replaying history.
- **Audit log** -- an append-only record of every state transition. No repository method updates or deletes a row.
- **Recovery scheduler** -- a periodic Celery task that finds executions stuck in `PROCESSING` past a threshold, marks them failed, and dispatches a fresh generation if retries remain.

## Architecture

Clean Architecture, dependency direction pointing inward:

```
interfaces (FastAPI routes, Redis consumer)
        v
   use_cases (business rules, depend only on Protocols)
        v
entities (Job, Execution, WorkUnit, Status, AuditLogEntry)
        ^
repositories (SQLAlchemy) -- services (Celery, document processing, LLM) -- frameworks (settings, wiring)
```

See [docs/Architecture.md](docs/Architecture.md) for the full design rationale and [docs/API.md](docs/API.md) for the HTTP API reference.

## Setup

```bash
cp .env.example .env          # edit as needed
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
docker compose up -d          # local Postgres (5544) + Redis (6380) for dev/tests
```

Run the API:

```bash
.venv/bin/python -m src.index
```

Run a worker and the recovery beat schedule:

```bash
.venv/bin/celery -A src.services.celery_tasks worker --loglevel=info
.venv/bin/celery -A src.services.celery_tasks beat --loglevel=info
```

Run the pub/sub ingestion consumer:

```bash
.venv/bin/python -c "
import asyncio
from src.frameworks.redis_client import create_redis_client
from src.frameworks.database import Database
from src.frameworks.settings import Settings
from src.interfaces.consumers.job_consumer import JobConsumer

settings = Settings.from_env()
consumer = JobConsumer(
    create_redis_client(settings.redis_url),
    settings.job_ingestion_channel,
    Database(settings).session_factory,
)
asyncio.run(consumer.run_forever())
"
```

## Testing

```bash
.venv/bin/pytest                              # unit tests only (no infra required)
docker compose up -d && .venv/bin/pytest      # unit + integration tests (real Postgres/Redis/Celery)
.venv/bin/mypy --strict src
.venv/bin/ruff check src
.venv/bin/black --check src
```

Integration tests (`src/tests/test_repositories.py`, `src/tests/test_integration.py`) are marked `@pytest.mark.integration` and skip automatically when the docker-compose services on ports 5544/6380 are not reachable.
