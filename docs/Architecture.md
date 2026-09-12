# Architecture

## Layering (Clean Architecture / DDD)

Dependencies point inward. Nothing in `entities` or `use-cases` imports from `interfaces`, `frameworks`, or a concrete `repositories` implementation — they depend only on the repository *interfaces* (`ILedgerRepository`, `IAllocationRepository`, `IConsumptionRepository`), which are implemented at the outer edge.

```
src/
├── shared/         # Branded types, domain constants, custom errors, Zod schemas, logger
├── entities/       # Pure domain models and logic: QuotaPool, Allocation, Consumption, Ledger, Balance
├── repositories/   # Data access: interfaces + Drizzle/Postgres implementations
├── use-cases/      # Business rules: ReserveQuota, RecordUsage, AllocateQuota, GetBalance, ...
├── interfaces/      # Express controllers and middleware (the HTTP boundary)
├── frameworks/     # Express app wiring, Drizzle schema + connection, JWT
└── tests/          # Unit tests (in-memory fakes) + integration tests (real Postgres)
```

This means every use case can be — and is — unit tested against an in-memory fake of its repository dependencies (`src/tests/testHelpers.ts`), with no database required. The same use cases are exercised again in `integration.test.ts` against the real Postgres-backed repositories, so the tests double as a contract check between the interface and its two implementations.

## Why the ledger is the source of truth

A quota system built around a mutable "remaining" counter has one number and no explanation. This system instead treats every quota-affecting event — an allocation, a reservation, a recorded consumption — as an immutable fact appended to a ledger table. Nothing in the codebase ever calls `UPDATE` or `DELETE` on a ledger row; `LedgerRepository.append` is the only write path, and `LedgerEntity.isTerminal()` documents that invariant on the domain model itself.

Balance is never stored as an independent number that could drift from that history. `BalanceEntity.fromLedger` and `replayLedger` (`src/entities/Ledger.ts`) are the single definition of "what do you owe": fold `allocated` entries up, `deallocated` entries down, `consumed` entries against the total, and ignore `reserved` entries for the total (they exist purely for audit visibility — see below). `GetBalance`, `ReserveQuota`, and `RecordUsage` all call through this same function, so there is exactly one place that could ever disagree with itself.

This is what makes dispute resolution mechanical rather than forensic: `GetAllocationHistory`/`GetBalance.getHistory` return the exact sequence of entries, in order, that produced a balance. Support can hand a customer that sequence instead of an assertion.

## Why enforcement is two-phase and asymmetric

Most of the resources this system meters (AI tokens, a file upload's final size) have a cost that is unknown until the operation *finishes*. A single "check-then-charge" gate can't work here, because there is nothing to charge yet at check time.

- **`ReserveQuota`** (coarse): refuses only if the available balance is already `<= 0`. It is intentionally permissive — it exists to stop new work once a scope is provably out of budget, not to predict the cost of the next operation.
- **`RecordUsage`** (precise): once the real cost is known, it is recorded exactly — but clamped to whatever remains (`BalanceEntity.clampToAvailable`), so a scope can never be driven net-negative no matter how much the coarse gate let through.

The consequence, stated plainly: a caller can overshoot by at most one operation's worth of cost. That is a deliberate, bounded trade-off, not an oversight — the alternative (blocking every operation until its cost is known) isn't available for the resources this system meters.

## Why allocation and consumption are separate from the ledger

`AllocationRepository` and `ConsumptionRepository` store *materialized* current totals per scope+resource. They are not sources of truth — they exist so that "how much has tenant X allocated to its users" or "how much has this user consumed" can be read in O(1) instead of replaying the full ledger on every request. Every write to them happens in the same use case that appends the corresponding ledger entry (`AllocateQuota` writes an `allocated`/`deallocated` entry and then updates `AllocationRepository`; `RecordUsage` writes a `consumed` entry and then updates `ConsumptionRepository`). If these materialized views were ever suspected of drifting, they can be rebuilt by replaying the ledger — they carry no information the ledger doesn't already have.

## Why the hierarchy is enforced at write time, not read time

`AllocateQuota.assertWithinTenantBudget` checks, before committing a sub-allocation to a user, that the sum of everything already promised to that tenant's other users plus the new amount does not exceed what the tenant itself was allocated (`AllocationInvariantError` otherwise). This is enforced once, at the moment budget moves down the hierarchy, rather than re-derived on every balance read — so a balance read stays a straightforward ledger replay for a single scope, and the hierarchy invariant lives in exactly one place.

## Scope and access control

`ScopeValidator` (`src/use-cases/ScopeValidator.ts`) is a pure function of `(Principal, requested Scope)` with three roles: `platform_admin` (any tenant), `tenant_admin` (their own tenant, any user within it), `user` (only their own scope). It has no framework dependency, so it's unit-testable in isolation; `interfaces/middleware/auth.ts` verifies the JWT and constructs the `Principal`, and every controller calls `ScopeValidator.assertCanAccess` before touching a use case.

## Cross-cutting concerns

- **Errors**: every domain failure extends `DomainError` (`src/shared/errors.ts`) and carries its own HTTP status and machine-readable `code`. `interfaces/middleware/errorHandler.ts` is the single place that translates a thrown error into an HTTP response, so controllers stay free of `try/catch` (`asyncHandler` forwards a rejected promise to it).
- **Rate limiting**: `RateLimiter` (`src/interfaces/middleware/rateLimiter.ts`) is a simple in-process fixed-window limiter keyed by tenant/user/resource. It's intentionally a small, swappable interface — a multi-instance deployment would back the same `tryConsume` contract with Redis instead.
- **Logging**: a single shared `pino` instance (`src/shared/logger.ts`) is used both directly (`index.ts`) and via `pino-http` for structured per-request logs (`interfaces/middleware/logging.ts`).
