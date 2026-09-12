import { BalanceEntity } from '../entities/Balance.js';
import type { ILedgerRepository } from '../repositories/LedgerRepository.js';
import { QuotaExhaustedError } from '../shared/errors.js';
import { zeroAmount, type ResourceType, type TenantId, type UserId } from '../shared/types.js';

export interface ReserveQuotaRequest {
  readonly tenantId: TenantId;
  readonly userId: UserId;
  readonly resourceType: ResourceType;
}

/**
 * The coarse pre-flight gate. The true cost of most operations (an AI
 * completion, a file upload) isn't known until it finishes, so this cannot
 * enforce an exact limit up front. Instead it asks one question: "is the
 * budget already at zero?" A caller can overshoot by at most one operation's
 * worth — RecordUsage clamps the actual charge to what's left afterward.
 */
export class ReserveQuota {
  constructor(private readonly ledgerRepository: ILedgerRepository) {}

  async execute(request: ReserveQuotaRequest): Promise<boolean> {
    const entries = await this.ledgerRepository.getAllForUser(request.tenantId, request.userId, request.resourceType);
    const balance = BalanceEntity.fromLedger(
      { tenantId: request.tenantId, userId: request.userId },
      request.resourceType,
      entries
    );

    if (balance.isExhausted()) {
      throw new QuotaExhaustedError(
        `Quota exhausted for tenant=${request.tenantId} user=${request.userId} resource=${request.resourceType}`
      );
    }

    // Record the reservation for audit visibility. It carries no amount and
    // never changes the balance — the real charge is recorded post-hoc.
    await this.ledgerRepository.append({
      tenantId: request.tenantId,
      userId: request.userId,
      resourceType: request.resourceType,
      entryType: 'reserved',
      amount: zeroAmount,
      balance: balance.available,
    });

    return true;
  }
}
