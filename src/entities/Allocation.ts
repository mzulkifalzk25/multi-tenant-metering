import {
  asAmount,
  scopeLevelOf,
  type Amount,
  type AllocationId,
  type ResourceType,
  type Scope,
  type ScopeLevel,
  type TenantId,
  type UserId,
} from '../shared/types.js';

/**
 * A committed budget at either the tenant or the user level. This is the
 * "promise" half of the model: how much a scope has been told it can spend.
 * Actual spend is tracked separately (see Consumption / the ledger) so that
 * the two can be compared, audited, and reconciled independently.
 */
export interface Allocation {
  readonly id: AllocationId;
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly allocated: Amount;
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export class AllocationEntity implements Allocation {
  readonly id: AllocationId;
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly allocated: Amount;
  readonly createdAt: Date;
  readonly updatedAt: Date;

  constructor(props: Allocation) {
    this.id = props.id;
    this.tenantId = props.tenantId;
    this.userId = props.userId;
    this.resourceType = props.resourceType;
    this.allocated = props.allocated;
    this.createdAt = props.createdAt;
    this.updatedAt = props.updatedAt;
  }

  /** Whether this allocation lives at the tenant level or a specific user's level. */
  level(): ScopeLevel {
    return scopeLevelOf(this.scope());
  }

  scope(): Scope {
    return this.userId ? { tenantId: this.tenantId, userId: this.userId } : { tenantId: this.tenantId };
  }

  /**
   * A parent scope may not commit more to its children than it has itself.
   * Given the sum already promised to siblings, is there room for one more
   * child allocation of `requested`?
   */
  canCoverChildAllocation(existingChildAllocations: Amount, requested: Amount): boolean {
    return existingChildAllocations + requested <= this.allocated;
  }

  withTopUp(amount: Amount, now: Date = new Date()): AllocationEntity {
    return new AllocationEntity({
      ...this,
      allocated: asAmount(this.allocated + amount),
      updatedAt: now,
    });
  }

  withReduction(amount: Amount, now: Date = new Date()): AllocationEntity {
    return new AllocationEntity({
      ...this,
      allocated: asAmount(Math.max(0, this.allocated - amount)),
      updatedAt: now,
    });
  }
}
