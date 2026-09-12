import { BalanceEntity, type Balance } from '../entities/Balance.js';
import type { ILedgerRepository } from './LedgerRepository.js';
import type { ResourceType, TenantId, UserId } from '../shared/types.js';

/**
 * Balance is never stored directly — it is always reconstructed by replaying
 * the immutable ledger for a scope+resource. This is what makes dispute
 * resolution possible: "here is every event that produced this number."
 */
export interface IBalanceRepository {
  getBalance(tenantId: TenantId, userId: UserId, resourceType: ResourceType): Promise<Balance>;
}

export class BalanceRepository implements IBalanceRepository {
  constructor(private readonly ledgerRepository: ILedgerRepository) {}

  async getBalance(tenantId: TenantId, userId: UserId, resourceType: ResourceType): Promise<Balance> {
    const entries = await this.ledgerRepository.getAllForUser(tenantId, userId, resourceType);
    return BalanceEntity.fromLedger({ tenantId, userId }, resourceType, entries);
  }
}
