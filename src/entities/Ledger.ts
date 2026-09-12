import {
  asAmount,
  type Amount,
  type LedgerEntryType,
  type LedgerId,
  type ResourceType,
  type TenantId,
  type UserId,
} from '../shared/types.js';

/**
 * One immutable fact about a quota change. The ledger is append-only: nothing
 * here is ever updated or deleted. Disputes are resolved by replaying the
 * sequence of entries, not by trusting a mutable counter.
 */
export interface LedgerEntry {
  readonly id: LedgerId;
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly entryType: LedgerEntryType;
  readonly amount: Amount;
  /** The available balance (allocated - consumed) immediately after this entry was applied. */
  readonly balance: Amount;
  readonly createdAt: Date;
  readonly reason?: string;
}

export class LedgerEntity implements LedgerEntry {
  readonly id: LedgerId;
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly entryType: LedgerEntryType;
  readonly amount: Amount;
  readonly balance: Amount;
  readonly createdAt: Date;
  readonly reason?: string;

  constructor(props: LedgerEntry) {
    this.id = props.id;
    this.tenantId = props.tenantId;
    this.userId = props.userId;
    this.resourceType = props.resourceType;
    this.entryType = props.entryType;
    this.amount = props.amount;
    this.balance = props.balance;
    this.createdAt = props.createdAt;
    this.reason = props.reason;
  }

  /** Ledger entries are terminal by construction: once appended, they cannot change. */
  isTerminal(): boolean {
    return true;
  }
}

export interface LedgerReplayResult {
  readonly allocated: Amount;
  readonly consumed: Amount;
  readonly available: Amount;
}

/**
 * The authoritative balance calculation. Given the complete ordered history
 * for a scope+resource, fold it into totals. This function is the single
 * place that defines what each entry type means; everything else (Balance,
 * GetBalance, dispute replays) calls through here so there is exactly one
 * definition of "what do you owe."
 */
export const replayLedger = (entries: readonly LedgerEntry[]): LedgerReplayResult => {
  let allocated = 0;
  let consumed = 0;

  for (const entry of entries) {
    switch (entry.entryType) {
      case 'allocated':
        allocated += entry.amount;
        break;
      case 'deallocated':
        allocated = Math.max(0, allocated - entry.amount);
        break;
      case 'consumed':
        consumed += entry.amount;
        break;
      case 'reserved':
        // Reservations are recorded for audit visibility only; the coarse
        // pre-flight gate never commits an amount because the true cost is
        // not known until the operation completes.
        break;
    }
  }

  return {
    allocated: asAmount(allocated),
    consumed: asAmount(consumed),
    available: asAmount(Math.max(0, allocated - consumed)),
  };
};
