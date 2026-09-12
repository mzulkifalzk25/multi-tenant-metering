# Architecture

## Layers

The codebase follows Clean Architecture: dependencies point inward, toward `entities`, and outer layers depend on inner-layer *Protocols*, never the reverse.

| Layer | Directory | Depends on | Knows about |
|---|---|---|---|
| Entities | `src/entities` | `src/shared` only | Domain rules and invariants |
| Use cases | `src/use_cases` | Entities, `protocols.py` | Business workflows; zero SQLAlchemy/Celery/FastAPI imports |
| Repositories | `src/repositories` | Entities, SQLAlchemy | Translating entities <-> ORM rows |
| Services | `src/services` | Use cases, repositories, Celery | Celery tasks, document processing, LLM calls |
| Frameworks | `src/frameworks` | Everything | Settings, DB/Redis wiring, FastAPI app, logging |
| Interfaces | `src/interfaces` | Use cases, frameworks | HTTP routes, the pub/sub consumer |

`src/use_cases/protocols.py` defines the ports (`JobRepositoryProtocol`, `DocumentProcessorProtocol`, `JobDispatcherProtocol`, `UnitOfWorkProtocol`, ...) that use cases depend on. Concrete repositories and services satisfy these structurally (no inheritance required), which is also how `src/tests/fixtures.py` provides in-memory fakes for unit tests without touching a database.

## Non-destructive retries: execution generations

A `Job` never mutates its own history. Every processing attempt is a separate `Execution` row with an incrementing `generation` number, referenced from `Job.execution_ids`. A failed generation is never edited or deleted -- a new one is created for the next attempt. This means:

- The full history of every attempt (including failed ones) is always inspectable via `GET /jobs/{tenant_id}/{job_id}`.
- The recovery scheduler can mark a stuck execution failed and dispatch a fresh generation without losing any information about what happened in the stuck one.

## Two retry paths

`ProcessJob.execute(job_id, tenant_id, execution_id=None)` supports two distinct kinds of retry:

1. **Idempotent resume** -- pass the *same* `execution_id`. This is what a Celery task retry does (transient failure, `self.retry()`), and it's also what happens if an execution generation reached `FAILED` and is deliberately retried in place: work units already `COMPLETED` are skipped, and `Status.FAILED -> EXECUTING` is an allowed transition specifically to support this. Calling `execute()` repeatedly for the same execution is always safe.
2. **Non-destructive retry** -- omit `execution_id` after a job's last execution reached a terminal state. A brand new generation is created; the old one is left untouched. This is what the recovery scheduler does for executions it judges stuck beyond simple resumption.

## Idempotent fan-out

A `WorkUnit`'s id is `WorkUnit.idempotency_key(execution_id, unit_type, unit_number)` -- deterministic, not a random UUID. `WorkUnitRepository.save_many` upserts on this key (Postgres `ON CONFLICT ... DO UPDATE`), so re-expanding the same execution generation (e.g. after a crash between "work units saved" and "status advanced to EXPANDED") never creates duplicate rows.

## Crash resumption: the UnitOfWork checkpoint

`ProcessJob` commits its own unit of work (`UnitOfWorkProtocol.commit()`) after each meaningful step: execution creation, work-unit expansion, and after *each* work unit's outcome (success or failure) -- not once at the very end. A hard crash (not just an exception -- a killed process) only loses work since the last checkpoint, and because expansion and units are keyed deterministically, resuming the same execution naturally skips whatever already committed.

## Per-item isolation

`ProcessJob._process_work_units` wraps each unit's processing in its own `try/except`. One page failing to process does not abort the other 199 pages in a PDF -- it's recorded as a `WorkUnitStatus.FAILED` with an error message, and the loop continues. The execution as a whole is marked `FAILED` only if *any* unit failed to complete, but every unit that could complete, did.

## Immutable audit log

`AuditRepository` exposes only `record()` (insert) and `list_by_job()` (read) -- no `update` or `delete`. `AuditLogEntry` is a frozen dataclass. Every state transition in `ProcessJob`, `IngestJob`, and `ScheduleRecovery` writes one entry, so the full causal history of a job is reconstructable from the audit log alone, independent of the current row state in `jobs`/`executions`/`work_units`.

## Tenant scoping

`JobRepository.get_by_id(job_id, tenant_id)` filters by tenant at the SQL level -- a job belonging to another tenant simply doesn't exist from that tenant's perspective (no existence leak via a 403 vs 404 distinction). `ScopeValidator` double-checks this invariant inside use cases as a defense-in-depth measure. The one exception is `get_by_id_unscoped`, reserved for the recovery scheduler, which is an internal process that must operate across all tenants.

## Retry/backoff policy

`compute_backoff_seconds(attempt, base_seconds, max_seconds)` computes `min(base * 2**attempt, max_seconds)`. Celery's `process_job_task` uses this for `self.retry(countdown=...)` on unexpected exceptions; the recovery scheduler uses `DEFAULT_MAX_RETRY_ATTEMPTS` to decide when a job has exhausted its retries and should be left `FAILED` permanently rather than dispatched again.

## Why Celery tasks call `asyncio.run()`

The domain and repository layers are fully async (SQLAlchemy 2.0 async + asyncpg). Celery tasks are synchronous by design, so each task opens its own event loop via `asyncio.run()` for the duration of one task invocation -- this is safe because a Celery worker thread never has a loop already running. (Testing this from `pytest-asyncio`'s own loop requires dispatching from a separate thread, matching how a real worker actually invokes the task -- see `test_process_job_task_via_celery_eager`.)
