import { and, eq, isNull } from 'drizzle-orm';
import { AllocationEntity, type Allocation } from '../entities/Allocation.js';
import { allocationsTable, getDb } from '../frameworks/database.js';
import {
  asAllocationId,
  asAmount,
  asTenantId,
  asUserId,
  type Amount,
  type ResourceType,
  type TenantId,
  type UserId,
} from '../shared/types.js';
import { generateId } from '../shared/utils.js';

export interface IAllocationRepository {
  findByScope(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType
  ): Promise<Allocation | undefined>;
  listByTenant(tenantId: TenantId, resourceType?: ResourceType): Promise<Allocation[]>;
  /** Upserts the committed amount for a scope+resource, called after an `allocated`/`deallocated` ledger entry. */
  setAllocated(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType,
    allocated: Amount
  ): Promise<Allocation>;
}

export class AllocationRepository implements IAllocationRepository {
  async findByScope(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType
  ): Promise<Allocation | undefined> {
    const db = getDb();
    const scopeCondition = userId ? eq(allocationsTable.userId, userId) : isNull(allocationsTable.userId);
    const [row] = await db
      .select()
      .from(allocationsTable)
      .where(
        and(eq(allocationsTable.tenantId, tenantId), scopeCondition, eq(allocationsTable.resourceType, resourceType))
      )
      .limit(1);
    return row ? toDomain(row) : undefined;
  }

  async listByTenant(tenantId: TenantId, resourceType?: ResourceType): Promise<Allocation[]> {
    const db = getDb();
    const condition = resourceType
      ? and(eq(allocationsTable.tenantId, tenantId), eq(allocationsTable.resourceType, resourceType))
      : eq(allocationsTable.tenantId, tenantId);
    const rows = await db.select().from(allocationsTable).where(condition);
    return rows.map(toDomain);
  }

  async setAllocated(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType,
    allocated: Amount
  ): Promise<Allocation> {
    const existing = await this.findByScope(tenantId, userId, resourceType);
    const db = getDb();
    const now = new Date();

    if (existing) {
      const [row] = await db
        .update(allocationsTable)
        .set({ allocated, updatedAt: now })
        .where(eq(allocationsTable.id, existing.id))
        .returning();
      if (!row) throw new Error('Allocation update did not return a row');
      return toDomain(row);
    }

    const [row] = await db
      .insert(allocationsTable)
      .values({
        id: generateId(),
        tenantId,
        userId: userId ?? null,
        resourceType,
        allocated,
        createdAt: now,
        updatedAt: now,
      })
      .returning();
    if (!row) throw new Error('Allocation insert did not return a row');
    return toDomain(row);
  }
}

interface AllocationRow {
  id: string;
  tenantId: string;
  userId: string | null;
  resourceType: string;
  allocated: number;
  createdAt: Date;
  updatedAt: Date;
}

const toDomain = (row: AllocationRow): AllocationEntity =>
  new AllocationEntity({
    id: asAllocationId(row.id),
    tenantId: asTenantId(row.tenantId),
    userId: row.userId ? asUserId(row.userId) : undefined,
    resourceType: row.resourceType as ResourceType,
    allocated: asAmount(row.allocated),
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  });
