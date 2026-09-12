# The Quota Model

## The hierarchy

Three levels, each a `Scope` (`{ tenantId, userId? }` — no `userId` means the tenant level itself):

```
Platform            (root — the total capacity per resource type, see QuotaPoolEntity)
  └─ Tenant          (an Allocation with userId omitted)
      └─ User        (an Allocation with userId set)
```

A resource is one of `storage`, `ai_tokens`, or `api_calls` (`ResourceType`, `src/shared/types.ts`); every allocation, reservation, and consumption is scoped to exactly one resource type as well as one scope.

## The four ledger entry types

Every change to a quota is one immutable `LedgerEntry` (`src/entities/Ledger.ts`). There are four kinds:

| `entryType`   | Written by      | Effect on balance                                  |
| ------------- | ---------------- | --------------------------------------------------- |
| `allocated`   | `AllocateQuota`  | Increases the scope's committed budget               |
| `deallocated` | `AllocateQuota`  | Decreases it (never below zero)                      |
| `consumed`    | `RecordUsage`    | Increases the amount actually spent                  |
| `reserved`    | `ReserveQuota`   | None — recorded for audit visibility only            |

`replayLedger` (`src/entities/Ledger.ts`) is the single function that folds a scope's entries into `{ allocated, consumed, available }`. `available = max(0, allocated - consumed)`. Every other place that needs a balance — `GetBalance`, `ReserveQuota`, `RecordUsage` — calls through this one function.

A `reserved` entry never changes the totals. It exists so that a dispute replay shows *when a caller was let through*, even though the actual charge (a `consumed` entry) is recorded separately, later, once the true cost is known. This is also why a single successful operation can produce two ledger entries: one `reserved` at the start, one `consumed` at the end.

## The two-phase enforcement walkthrough

```
1. Client calls ReserveQuota.execute({ tenantId, userId, resourceType })
     -> replay the ledger for this scope+resource
     -> if available <= 0: throw QuotaExhaustedError
     -> else: append a `reserved` entry (amount 0, balance unchanged), return true

2. Client performs the actual operation (calls an LLM, writes a file, ...)
     -> now the real cost is known

3. Client calls RecordUsage.execute({ tenantId, userId, resourceType, amount: <real cost> })
     -> replay the ledger again to get the current balance
     -> recordedAmount = min(amount, available)   -- clamp, never go negative
     -> append a `consumed` entry for recordedAmount
     -> increment the ConsumptionRepository materialized total
```

Because the coarse gate in step 1 only checks `available <= 0`, and the real charge in step 3 is clamped to whatever's left, the worst case is: a scope with `available = 1` is allowed to start one more operation, which might cost far more than `1` — that operation is charged only the `1` that was left, and the *next* `ReserveQuota` call for that scope will refuse. This is the bounded, one-operation overshoot the model accepts by design (see [Architecture.md](Architecture.md) for the rationale).

## Allocating budget down the hierarchy

`AllocateQuota.execute({ tenantId, userId?, resourceType, amount })`:

- **No `userId`** — allocating from the platform to the tenant. Always succeeds (the platform pool ceiling is a separate, coarser concern — see `QuotaPoolEntity` — not enforced per-allocation call).
- **With `userId`** — sub-allocating from the tenant to one of its users. Before committing, `assertWithinTenantBudget` sums every *other* user's current allocation for that tenant+resource and checks that `existingChildTotal + amount <= tenantBudget` (the tenant's own `allocated` total). If it doesn't fit, `AllocationInvariantError` is thrown and nothing is written. A negative `amount` (reducing a user's allocation) always succeeds — freeing budget can never violate the invariant.

A positive `amount` appends an `allocated` entry; a negative one appends `deallocated` with the absolute value. Either way, `AllocationRepository.setAllocated` is updated to the new total in the same call, so a subsequent `findByScope`/`listByTenant` read doesn't need to replay the ledger.

## Resolving a billing dispute

Because nothing is ever mutated or deleted, a dispute ("why was I charged X") is answered by calling `GetBalance.getHistory` (per user+resource) or `GetAllocationHistory` (the whole tenant, across all its users) and handing back the literal sequence of ledger entries — `allocated`/`deallocated`/`reserved`/`consumed`, each with its own `amount`, resulting `balance`, timestamp, and optional `reason`. The number in dispute is always reproducible by folding that sequence through `replayLedger` — there is no separate "true" balance to reconcile against.
