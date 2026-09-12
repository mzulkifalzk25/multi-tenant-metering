import { LedgerEntry, replayLedger } from './Ledger.js';
import { asAmount, type Amount, type ResourceType, type Scope, type TenantId, type UserId } from '../shared/types.js';

/**
 * The reconstructed financial state of a scope+resource at a point in time:
 * how much was promised, how much has been spent, and what's left. This is
 * always derived by replaying the ledger — never stored as an independently
 * mutable counter — so it can never drift from the audit trail.
 */
export interface Balance {
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly allocated: Amount;
  readonly consumed: Amount;
  readonly available: Amount;
  readonly asOf: Date;
}

export class BalanceEntity implements Balance {
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly allocated: Amount;
  readonly consumed: Amount;
  readonly available: Amount;
  readonly asOf: Date;

  constructor(props: Balance) {
    this.tenantId = props.tenantId;
    this.userId = props.userId;
    this.resourceType = props.resourceType;
    this.allocated = props.allocated;
    this.consumed = props.consumed;
    this.available = props.available;
    this.asOf = props.asOf;
  }

  static fromLedger(
    scope: Scope,
    resourceType: ResourceType,
    entries: readonly LedgerEntry[],
    asOf: Date = new Date()
  ): BalanceEntity {
    const { allocated, consumed, available } = replayLedger(entries);
    return new BalanceEntity({
      tenantId: scope.tenantId,
      userId: scope.userId,
      resourceType,
      allocated,
      consumed,
      available,
      asOf,
    });
  }

  /** The coarse pre-flight rule: refuse only once the budget is fully spent. */
  isExhausted(): boolean {
    return this.available <= 0;
  }

  /** How much of `amount` can actually be charged against this balance right now. */
  clampToAvailable(amount: Amount): Amount {
    return asAmount(Math.min(amount, this.available));
  }
}
