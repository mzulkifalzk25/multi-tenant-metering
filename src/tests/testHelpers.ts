import { LedgerEntity, type LedgerEntry } from '../entities/Ledger.js';
import { AllocationEntity, type Allocation } from '../entities/Allocation.js';
import { ConsumptionEntity, type Consumption } from '../entities/Consumption.js';
import type { IAllocationRepository } from '../repositories/AllocationRepository.js';
import type { IConsumptionRepository } from '../repositories/ConsumptionRepository.js';
import type { ILedgerRepository, NewLedgerEntry } from '../repositories/LedgerRepository.js';
import {
  asAllocationId,
  asAmount,
  asLedgerId,
  type Amount,
  type ResourceType,
  type TenantId,
  type UserId,
} from '../shared/types.js';
import { generateId } from '../shared/utils.js';

/**
 * In-memory stand-ins for the repository interfaces, used by unit and
 * use-case tests so they exercise real business logic without a live
 * Postgres instance. Integration tests (src/tests/integration.test.ts) use
 * the real Drizzle-backed repositories against an actual database instead.
 */
export class InMemoryLedgerRepository implements ILedgerRepository {
  readonly entries: LedgerEntry[] = [];

  async append(entry: NewLedgerEntry): Promise<LedgerEntry> {
    const created = new LedgerEntity({
      id: asLedgerId(generateId()),
      tenantId: entry.tenantId,
      userId: entry.userId,
      resourceType: entry.resourceType,
      entryType: entry.entryType,
      amount: entry.amount,
      balance: entry.balance,
      createdAt: new Date(),
      reason: entry.reason,
    });
    this.entries.push(created);
    return created;
  }

  async getAllForUser(tenantId: TenantId, userId: UserId, resourceType: ResourceType): Promise<LedgerEntry[]> {
    return this.entries.filter(
      (entry) => entry.tenantId === tenantId && entry.userId === userId && entry.resourceType === resourceType
    );
  }

  async getAllForTenant(tenantId: TenantId, resourceType?: ResourceType): Promise<LedgerEntry[]> {
    return this.entries.filter(
      (entry) => entry.tenantId === tenantId && (!resourceType || entry.resourceType === resourceType)
    );
  }
}

export class InMemoryAllocationRepository implements IAllocationRepository {
  private readonly rows = new Map<string, Allocation>();

  private key(tenantId: TenantId, userId: UserId | undefined, resourceType: ResourceType): string {
    return `${tenantId}:${userId ?? '-'}:${resourceType}`;
  }

  async findByScope(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType
  ): Promise<Allocation | undefined> {
    return this.rows.get(this.key(tenantId, userId, resourceType));
  }

  async listByTenant(tenantId: TenantId, resourceType?: ResourceType): Promise<Allocation[]> {
    return [...this.rows.values()].filter(
      (allocation) => allocation.tenantId === tenantId && (!resourceType || allocation.resourceType === resourceType)
    );
  }

  async setAllocated(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType,
    allocated: Amount
  ): Promise<Allocation> {
    const key = this.key(tenantId, userId, resourceType);
    const existing = this.rows.get(key);
    const now = new Date();
    const updated = new AllocationEntity({
      id: existing?.id ?? asAllocationId(generateId()),
      tenantId,
      userId,
      resourceType,
      allocated,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
    });
    this.rows.set(key, updated);
    return updated;
  }
}

export class InMemoryConsumptionRepository implements IConsumptionRepository {
  private readonly rows = new Map<string, Consumption>();

  private key(tenantId: TenantId, userId: UserId | undefined, resourceType: ResourceType): string {
    return `${tenantId}:${userId ?? '-'}:${resourceType}`;
  }

  async findByScope(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType
  ): Promise<Consumption | undefined> {
    return this.rows.get(this.key(tenantId, userId, resourceType));
  }

  async increment(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType,
    amount: Amount
  ): Promise<Consumption> {
    const key = this.key(tenantId, userId, resourceType);
    const existing = this.rows.get(key);
    const updated = new ConsumptionEntity({
      tenantId,
      userId,
      resourceType,
      consumed: asAmount((existing?.consumed ?? 0) + amount),
      updatedAt: new Date(),
    });
    this.rows.set(key, updated);
    return updated;
  }
}
