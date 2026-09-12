import type { Balance } from '../entities/Balance.js';
import { BalanceEntity } from '../entities/Balance.js';
import type { LedgerEntry } from '../entities/Ledger.js';
import type { ILedgerRepository } from '../repositories/LedgerRepository.js';
import type { ResourceType, TenantId, UserId } from '../shared/types.js';

export interface BalanceRequest {
  readonly tenantId: TenantId;
  readonly userId: UserId;
  readonly resourceType: ResourceType;
}

/**
 * Reconstructs balance by replaying the immutable ledger. This is
 * authoritative by construction: there is no separately-mutable counter for
 * it to drift from.
 */
export class GetBalance {
  constructor(private readonly ledgerRepository: ILedgerRepository) {}

  async execute(request: BalanceRequest): Promise<Balance> {
    const entries = await this.ledgerRepository.getAllForUser(request.tenantId, request.userId, request.resourceType);
    return BalanceEntity.fromLedger(
      { tenantId: request.tenantId, userId: request.userId },
      request.resourceType,
      entries
    );
  }

  /** The full event history behind a balance — what a billing dispute is resolved with. */
  async getHistory(request: BalanceRequest): Promise<LedgerEntry[]> {
    return this.ledgerRepository.getAllForUser(request.tenantId, request.userId, request.resourceType);
  }
}
