# Multi-Tenant Metering

A production-grade hierarchical quota system with an immutable audit ledger, built with strict TypeScript, Express, Drizzle ORM, and PostgreSQL.

## The problem

Most quota systems are a mutable counter:

```
quota = 1000
if quota < 100: deny
quota -= amount
```

This breaks down as soon as:

- **The cost isn't known until the operation finishes** (an AI completion's token count, a file upload's final size). You can't debit up front because you don't yet know the amount.
- **A customer disputes a bill.** A single number has no explanation. You need "here is every event that produced this balance," not just the balance itself.
- **Quota needs to nest.** A platform gives tenants a budget; tenants give their own users a slice of it. A plain counter per user has no way to express or enforce that hierarchy.

## The solution

**A hierarchical allocation model** (Platform -> Tenant -> User) plus **two-phase enforcement** backed by an **immutable, append-only ledger**.

```
Platform Pool (per resource type: storage / ai_tokens / api_calls)
  └─ Tenant allocation (promised budget, committed from the platform)
      ├─ User allocation (promised budget, committed from the tenant)
      └─ User allocation
```

**Phase 1 — coarse pre-flight gate** (`ReserveQuota`): before an operation starts, refuse only if the balance is already at or below zero. This is deliberately coarse because the true cost isn't known yet.

**Phase 2 — precise post-hoc recording** (`RecordUsage`): once the operation completes and its real cost is known, charge exactly that amount — clamped to whatever headroom remains, so a caller can never go net-negative.

The result: a caller can overshoot by at most one operation's worth, and every allocation, reservation, and consumption is a permanent entry in the ledger. Balances are never stored as an independently-mutable number — they are always reconstructed by replaying the ledger, which is what makes disputes resolvable and audits trustworthy.

See [docs/QuotaModel.md](docs/QuotaModel.md) for the full model and [docs/Architecture.md](docs/Architecture.md) for the Clean Architecture layout and design decisions.

## Setup

```bash
npm install
cp .env.example .env        # edit as needed
npm run db:up                # starts Postgres via docker-compose on localhost:5544
npx drizzle-kit generate:pg  # generate SQL from the schema in src/frameworks/database.ts
psql "$DATABASE_URL" -f drizzle/<generated>.sql   # apply it
npm run dev
```

## API

All endpoints (except `/health`) require `Authorization: Bearer <jwt>`, where the token carries `{ role, tenantId?, userId? }` (see `src/frameworks/auth.ts`). Access is scoped: a `user` may only act on their own `userId`; a `tenant_admin` may act on any user within their own `tenantId`; a `platform_admin` may act on anything.

| Method | Path             | Purpose                                                          |
| ------ | ---------------- | ----------------------------------------------------------------- |
| GET    | `/health`        | Liveness probe                                                    |
| POST   | `/quota/allocate`| Commit budget: platform → tenant, or tenant → user                |
| POST   | `/quota/reserve` | Coarse pre-flight gate — may this operation start?                |
| POST   | `/quota/record`  | Precise post-hoc recording of an operation's actual cost          |
| GET    | `/quota/balance` | Reconstructed balance for a `tenantId`/`userId`/`resourceType`    |
| GET    | `/quota/history` | Full ledger entries behind a balance — used to resolve disputes   |

## Testing

```bash
npm test                 # unit tests — no database required
npm run db:up             # start Postgres for integration tests
DATABASE_URL=postgresql://metering:metering@localhost:5544/metering npm run test:integration
```

`src/tests/integration.test.ts` exercises the real Drizzle-backed repositories against a live PostgreSQL instance (allocate → reserve → record → balance → dispute replay). It skips automatically when `DATABASE_URL` is not set, so `npm test` never requires Docker.

```bash
npx tsc --noEmit    # type-check (strict mode, no `any`)
npm run lint        # ESLint
npm run format:check # Prettier
npm run build        # compile to dist/
```

## Project layout

Clean Architecture, dependencies pointing inward:

```
interfaces (Express controllers, middleware)
        v
  use-cases (business rules: ReserveQuota, RecordUsage, AllocateQuota, GetBalance, ...)
        v
   entities (QuotaPool, Allocation, Consumption, Ledger, Balance — pure domain logic)
        ^
repositories (Drizzle/Postgres) -- frameworks (Express app, DB connection, JWT)
```
