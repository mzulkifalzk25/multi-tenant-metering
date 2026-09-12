import type { Amount, ResourceType, TenantId, UserId } from '../shared/types.js';

/**
 * A materialized view of "how much has actually been spent" for a scope and
 * resource. This is a read-model derived from `consumed` ledger entries; the
 * ledger remains the source of truth, this is a cache kept in sync for fast
 * reads without replaying the full history on every request.
 */
export interface Consumption {
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly consumed: Amount;
  readonly updatedAt: Date;
}

export class ConsumptionEntity implements Consumption {
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly consumed: Amount;
  readonly updatedAt: Date;

  constructor(props: Consumption) {
    this.tenantId = props.tenantId;
    this.userId = props.userId;
    this.resourceType = props.resourceType;
    this.consumed = props.consumed;
    this.updatedAt = props.updatedAt;
  }
}
