# API Reference

All endpoints require `X-Tenant-Id` (and, for submission, `X-User-Id`) headers identifying the caller. The `{tenant_id}` path segment must match the authenticated `X-Tenant-Id` header exactly, or the request is rejected with `403` before any data access happens.

## `POST /jobs/{tenant_id}/submit`

Submit a document for processing.

**Headers:** `X-Tenant-Id`, `X-User-Id`

**Body:**

```json
{
  "file_path": "/uploads/report.pdf",
  "file_type": "pdf"
}
```

`file_type` is one of `pdf`, `image`, `video`.

**Response `200`:**

```json
{
  "job_id": "5f1c...",
  "status": "pending"
}
```

**Errors:**

| Status | Cause |
|---|---|
| `401` | Missing `X-Tenant-Id` / `X-User-Id` header |
| `403` | Path `tenant_id` does not match `X-Tenant-Id` |
| `404` | Tenant does not exist |
| `422` | Malformed body (e.g. unknown `file_type`) |

Submitting enqueues processing via Celery; the response returns immediately with the job in `pending` status.

## `GET /jobs/{tenant_id}/{job_id}`

Fetch a job's full history: every execution generation, each generation's work units, and the complete audit log.

**Headers:** `X-Tenant-Id`

**Response `200`:**

```json
{
  "job_id": "5f1c...",
  "tenant_id": "acme",
  "status": "completed",
  "file_type": "pdf",
  "created_at": "2026-01-01T00:00:00Z",
  "executions": [
    {
      "id": "5f1c...::gen-0",
      "generation": 0,
      "status": "completed",
      "started_at": "2026-01-01T00:00:01Z",
      "completed_at": "2026-01-01T00:00:05Z",
      "work_units": [
        {"id": "...", "unit_type": "page", "unit_number": 0, "status": "completed", "error": null}
      ]
    }
  ],
  "audit_log": [
    {"id": "...", "event_type": "job_ingested", "message": "...", "created_at": "..."},
    {"id": "...", "event_type": "execution_started", "message": "...", "created_at": "..."},
    {"id": "...", "event_type": "execution_completed", "message": "...", "created_at": "..."}
  ]
}
```

**Errors:**

| Status | Cause |
|---|---|
| `401` | Missing `X-Tenant-Id` header |
| `403` | Path `tenant_id` does not match `X-Tenant-Id` |
| `404` | Job does not exist (including: exists, but for a different tenant) |

## `GET /health`

Liveness/readiness check. Pings the database (`SELECT 1`) and Redis (`PING`); never raises.

```json
{"status": "ok", "database": "ok", "redis": "ok"}
```

`status` is `"degraded"` if either dependency is unreachable.
