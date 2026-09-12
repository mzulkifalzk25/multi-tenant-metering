/**
 * Branded primitives. Plain strings/numbers are structurally interchangeable in
 * TypeScript, which is how a TenantId ends up where a UserId belongs. Branding
 * makes that a compile error instead of a production incident.
 */
type Brand<T, B extends string> = T & { readonly __brand: B };

export type TenantId = Brand<string, 'TenantId'>;
export type UserId = Brand<string, 'UserId'>;
export type AllocationId = Brand<string, 'AllocationId'>;
export type LedgerId = Brand<string, 'LedgerId'>;
export type PoolId = Brand<string, 'PoolId'>;

export const asTenantId = (value: string): TenantId => value as TenantId;
export const asUserId = (value: string): UserId => value as UserId;
export const asAllocationId = (value: string): AllocationId => value as AllocationId;
export const asLedgerId = (value: string): LedgerId => value as LedgerId;
export const asPoolId = (value: string): PoolId => value as PoolId;

/** The three resource types this metering system tracks and bills. */
export const RESOURCE_TYPES = ['storage', 'ai_tokens', 'api_calls'] as const;
export type ResourceType = (typeof RESOURCE_TYPES)[number];

/**
 * A scope identifies "whose" quota an operation concerns, at one of the three
 * levels in the Platform -> Tenant -> User hierarchy. A scope without a
 * userId means the operation is at the tenant level.
 */
export interface Scope {
  readonly tenantId: TenantId;
  readonly userId?: UserId;
}

export type ScopeLevel = 'platform' | 'tenant' | 'user';

export const scopeLevelOf = (scope: Scope): ScopeLevel => (scope.userId ? 'user' : 'tenant');

/** Every mutation to a quota is recorded as one of these immutable event kinds. */
export const LEDGER_ENTRY_TYPES = ['allocated', 'deallocated', 'consumed', 'reserved'] as const;
export type LedgerEntryType = (typeof LEDGER_ENTRY_TYPES)[number];

/** A non-negative quantity of a resource. Branded to avoid mixing with raw counts. */
export type Amount = Brand<number, 'Amount'>;

export const asAmount = (value: number): Amount => {
  if (!Number.isFinite(value) || value < 0) {
    throw new RangeError(`Amount must be a finite, non-negative number, got ${value}`);
  }
  return value as Amount;
};

export const zeroAmount = asAmount(0);
