import { and, eq, isNull, sql } from 'drizzle-orm';
import { ConsumptionEntity, type Consumption } from '../entities/Consumption.js';
import { consumptionsTable, getDb } from '../frameworks/database.js';
import {
  asAmount,
  asTenantId,
  asUserId,
  type Amount,
  type ResourceType,
  type TenantId,
  type UserId,
} from '../shared/types.js';

export interface IConsumptionRepository {
  findByScope(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType
  ): Promise<Consumption | undefined>;
  /** Adds `amount` to the running total for a scope+resource, creating the row on first use. */
  increment(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType,
    amount: Amount
  ): Promise<Consumption>;
}

export class ConsumptionRepository implements IConsumptionRepository {
  async findByScope(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType
  ): Promise<Consumption | undefined> {
    const db = getDb();
    const scopeCondition = userId ? eq(consumptionsTable.userId, userId) : isNull(consumptionsTable.userId);
    const [row] = await db
      .select()
      .from(consumptionsTable)
      .where(
        and(eq(consumptionsTable.tenantId, tenantId), scopeCondition, eq(consumptionsTable.resourceType, resourceType))
      )
      .limit(1);
    return row ? toDomain(row) : undefined;
  }

  async increment(
    tenantId: TenantId,
    userId: UserId | undefined,
    resourceType: ResourceType,
    amount: Amount
  ): Promise<Consumption> {
    const db = getDb();
    const now = new Date();
    const existing = await this.findByScope(tenantId, userId, resourceType);

    if (existing) {
      const scopeCondition = userId ? eq(consumptionsTable.userId, userId) : isNull(consumptionsTable.userId);
      const [row] = await db
        .update(consumptionsTable)
        .set({ consumed: sql`${consumptionsTable.consumed} + ${amount}`, updatedAt: now })
        .where(
          and(
            eq(consumptionsTable.tenantId, tenantId),
            scopeCondition,
            eq(consumptionsTable.resourceType, resourceType)
          )
        )
        .returning();
      if (!row) throw new Error('Consumption update did not return a row');
      return toDomain(row);
    }

    const [row] = await db
      .insert(consumptionsTable)
      .values({ tenantId, userId: userId ?? null, resourceType, consumed: amount, updatedAt: now })
      .returning();
    if (!row) throw new Error('Consumption insert did not return a row');
    return toDomain(row);
  }
}

interface ConsumptionRow {
  tenantId: string;
  userId: string | null;
  resourceType: string;
  consumed: number;
  updatedAt: Date;
}

const toDomain = (row: ConsumptionRow): ConsumptionEntity =>
  new ConsumptionEntity({
    tenantId: asTenantId(row.tenantId),
    userId: row.userId ? asUserId(row.userId) : undefined,
    resourceType: row.resourceType as ResourceType,
    consumed: asAmount(row.consumed),
    updatedAt: row.updatedAt,
  });
