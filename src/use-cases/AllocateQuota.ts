import type { Allocation } from '../entities/Allocation.js';
import type { IAllocationRepository } from '../repositories/AllocationRepository.js';
import type { ILedgerRepository } from '../repositories/LedgerRepository.js';
import { AllocationInvariantError } from '../shared/errors.js';
import { asAmount, type Amount, type ResourceType, type TenantId, type UserId } from '../shared/types.js';

export interface AllocateQuotaRequest {
  readonly tenantId: TenantId;
  /** Omit to allocate at the tenant level (from the platform); provide to sub-allocate to a user. */
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  /** The amount to add to (or, if negative, remove from) the current commitment. */
  readonly amount: number;
  readonly reason?: string;
}

/**
 * Commits budget down the hierarchy: platform -> tenant, or tenant -> user.
 * A tenant may never sub-allocate to its users more than it was itself
 * allocated — that invariant is what makes the hierarchy meaningful instead
 * of every level being an independent, uncoordinated counter.
 */
export class AllocateQuota {
  constructor(
    private readonly ledgerRepository: ILedgerRepository,
    private readonly allocationRepository: IAllocationRepository
  ) {}

  async execute(request: AllocateQuotaRequest): Promise<Allocation> {
    if (request.userId) {
      await this.assertWithinTenantBudget(request.tenantId, request.userId, request.resourceType, request.amount);
    }

    const current = await this.allocationRepository.findByScope(request.tenantId, request.userId, request.resourceType);
    const currentAllocated = current?.allocated ?? 0;
    const nextAllocated = asAmount(Math.max(0, currentAllocated + request.amount));

    await this.ledgerRepository.append({
      tenantId: request.tenantId,
      userId: request.userId,
      resourceType: request.resourceType,
      entryType: request.amount >= 0 ? 'allocated' : 'deallocated',
      amount: asAmount(Math.abs(request.amount)),
      balance: nextAllocated,
      reason: request.reason,
    });

    return this.allocationRepository.setAllocated(
      request.tenantId,
      request.userId,
      request.resourceType,
      nextAllocated
    );
  }

  private async assertWithinTenantBudget(
    tenantId: TenantId,
    userId: UserId,
    resourceType: ResourceType,
    delta: number
  ): Promise<void> {
    if (delta <= 0) {
      // Reducing a user's allocation never threatens the parent's budget.
      return;
    }

    const tenantAllocation = await this.allocationRepository.findByScope(tenantId, undefined, resourceType);
    const tenantBudget: Amount = tenantAllocation?.allocated ?? asAmount(0);

    const childAllocations = await this.allocationRepository.listByTenant(tenantId, resourceType);
    const existingChildTotal = childAllocations
      .filter(
        (allocation): allocation is Allocation & { userId: UserId } =>
          allocation.userId !== undefined && allocation.userId !== userId
      )
      .reduce((sum, allocation) => sum + allocation.allocated, 0);

    if (existingChildTotal + delta > tenantBudget) {
      throw new AllocationInvariantError(
        `Allocating ${delta} to user=${userId} would exceed tenant=${tenantId}'s ${resourceType} budget of ${tenantBudget} (already committed: ${existingChildTotal})`
      );
    }
  }
}
