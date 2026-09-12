import { asAmount, type Amount, type PoolId, type ResourceType } from '../shared/types.js';

/**
 * The platform-level ceiling for a resource type: the total budget that can
 * ever be allocated out to tenants. This is the root of the hierarchy —
 * Platform Pool -> Tenant allocations -> User allocations.
 */
export interface QuotaPool {
  readonly id: PoolId;
  readonly resourceType: ResourceType;
  readonly capacity: Amount;
  /** Sum of everything currently allocated to tenants out of this pool. */
  readonly allocatedToTenants: Amount;
}

export class QuotaPoolEntity implements QuotaPool {
  readonly id: PoolId;
  readonly resourceType: ResourceType;
  readonly capacity: Amount;
  readonly allocatedToTenants: Amount;

  constructor(props: QuotaPool) {
    this.id = props.id;
    this.resourceType = props.resourceType;
    this.capacity = props.capacity;
    this.allocatedToTenants = props.allocatedToTenants;
  }

  remaining(): Amount {
    return asAmount(Math.max(0, this.capacity - this.allocatedToTenants));
  }

  canAllocate(amount: Amount): boolean {
    return this.allocatedToTenants + amount <= this.capacity;
  }
}
