/** Base class for every domain-level error, carrying an HTTP status and a machine-readable code. */
export abstract class DomainError extends Error {
  abstract readonly statusCode: number;
  abstract readonly code: string;

  constructor(message: string) {
    super(message);
    this.name = new.target.name;
    Error.captureStackTrace?.(this, new.target);
  }
}

/** The request itself is malformed or fails schema validation. */
export class ValidationError extends DomainError {
  readonly statusCode = 400;
  readonly code = 'VALIDATION_ERROR';
}

/** The caller is not permitted to act on the requested tenant/user scope. */
export class ScopeAccessError extends DomainError {
  readonly statusCode = 403;
  readonly code = 'SCOPE_ACCESS_DENIED';
}

/** The referenced tenant, user, allocation, or ledger entry does not exist. */
export class NotFoundError extends DomainError {
  readonly statusCode = 404;
  readonly code = 'NOT_FOUND';
}

/** The pre-flight coarse gate refused because the balance is already at or below zero. */
export class QuotaExhaustedError extends DomainError {
  readonly statusCode = 429;
  readonly code = 'QUOTA_EXHAUSTED';
}

/** The caller exceeded the configured request rate for this scope/resource. */
export class RateLimitExceededError extends DomainError {
  readonly statusCode = 429;
  readonly code = 'RATE_LIMIT_EXCEEDED';
}

/** An allocation would violate hierarchical invariants (e.g. child exceeds parent's remaining budget). */
export class AllocationInvariantError extends DomainError {
  readonly statusCode = 409;
  readonly code = 'ALLOCATION_INVARIANT_VIOLATION';
}

export const isDomainError = (error: unknown): error is DomainError => error instanceof DomainError;
