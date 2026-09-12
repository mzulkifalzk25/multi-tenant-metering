import { BalanceEntity } from '../entities/Balance.js';
import type { IConsumptionRepository } from '../repositories/ConsumptionRepository.js';
import type { ILedgerRepository } from '../repositories/LedgerRepository.js';
import { asAmount, type Amount, type ResourceType, type TenantId, type UserId } from '../shared/types.js';

export interface RecordUsageRequest {
  readonly tenantId: TenantId;
  readonly userId: UserId;
  readonly resourceType: ResourceType;
  /** The actual cost of the operation, known only after it completed. */
  readonly amount: number;
  readonly reason?: string;
}

export interface RecordUsageResult {
  readonly recordedAmount: Amount;
  readonly balanceAfter: Amount;
}

/**
 * The precise post-hoc recording half of the two-phase model. Whatever the
 * operation actually cost, only what remained in the budget is charged —
 * clamped to zero-or-more headroom — so a user can never go net negative no
 * matter how much the coarse gate let through.
 */
export class RecordUsage {
  constructor(
    private readonly ledgerRepository: ILedgerRepository,
    private readonly consumptionRepository: IConsumptionRepository
  ) {}

  async execute(request: RecordUsageRequest): Promise<RecordUsageResult> {
    const requestedAmount = asAmount(request.amount);
    const entries = await this.ledgerRepository.getAllForUser(request.tenantId, request.userId, request.resourceType);
    const balanceBefore = BalanceEntity.fromLedger(
      { tenantId: request.tenantId, userId: request.userId },
      request.resourceType,
      entries
    );

    const recordedAmount = balanceBefore.clampToAvailable(requestedAmount);
    const balanceAfter = asAmount(balanceBefore.available - recordedAmount);

    await this.ledgerRepository.append({
      tenantId: request.tenantId,
      userId: request.userId,
      resourceType: request.resourceType,
      entryType: 'consumed',
      amount: recordedAmount,
      balance: balanceAfter,
      reason: request.reason,
    });

    await this.consumptionRepository.increment(request.tenantId, request.userId, request.resourceType, recordedAmount);

    return { recordedAmount, balanceAfter };
  }
}
