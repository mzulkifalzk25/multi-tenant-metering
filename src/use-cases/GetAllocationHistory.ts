import type { LedgerEntry } from '../entities/Ledger.js';
import type { ILedgerRepository } from '../repositories/LedgerRepository.js';
import type { ResourceType, TenantId } from '../shared/types.js';

export interface AllocationHistoryRequest {
  readonly tenantId: TenantId;
  readonly resourceType?: ResourceType;
}

/**
 * Every ledger entry for a tenant (its own allocations plus every user
 * beneath it), in order. This is the tenant-wide view used to resolve
 * billing disputes and produce usage reports.
 */
export class GetAllocationHistory {
  constructor(private readonly ledgerRepository: ILedgerRepository) {}

  async execute(request: AllocationHistoryRequest): Promise<LedgerEntry[]> {
    return this.ledgerRepository.getAllForTenant(request.tenantId, request.resourceType);
  }
}
