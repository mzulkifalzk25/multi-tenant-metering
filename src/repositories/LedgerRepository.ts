import { and, asc, eq } from 'drizzle-orm';
import { LedgerEntity, type LedgerEntry } from '../entities/Ledger.js';
import { getDb, ledgerTable } from '../frameworks/database.js';
import {
  asAmount,
  asLedgerId,
  asTenantId,
  asUserId,
  type Amount,
  type LedgerEntryType,
  type ResourceType,
  type TenantId,
  type UserId,
} from '../shared/types.js';
import { generateId } from '../shared/utils.js';

export interface NewLedgerEntry {
  readonly tenantId: TenantId;
  readonly userId?: UserId;
  readonly resourceType: ResourceType;
  readonly entryType: LedgerEntryType;
  readonly amount: Amount;
  readonly balance: Amount;
  readonly reason?: string;
}

/**
 * The ledger is append-only by contract: this interface exposes no update or
 * delete. Every implementation (Postgres-backed or in-memory, for tests)
 * must uphold that — corrections happen by appending a compensating entry,
 * never by rewriting history.
 */
export interface ILedgerRepository {
  append(entry: NewLedgerEntry): Promise<LedgerEntry>;
  getAllForUser(tenantId: TenantId, userId: UserId, resourceType: ResourceType): Promise<LedgerEntry[]>;
  getAllForTenant(tenantId: TenantId, resourceType?: ResourceType): Promise<LedgerEntry[]>;
}

export class LedgerRepository implements ILedgerRepository {
  async append(entry: NewLedgerEntry): Promise<LedgerEntry> {
    const db = getDb();
    const row = {
      id: generateId(),
      tenantId: entry.tenantId,
      userId: entry.userId ?? null,
      resourceType: entry.resourceType,
      entryType: entry.entryType,
      amount: entry.amount,
      balance: entry.balance,
      reason: entry.reason ?? null,
    };
    const [inserted] = await db.insert(ledgerTable).values(row).returning();
    if (!inserted) {
      throw new Error('Ledger insert did not return a row');
    }
    return toDomain(inserted);
  }

  async getAllForUser(tenantId: TenantId, userId: UserId, resourceType: ResourceType): Promise<LedgerEntry[]> {
    const db = getDb();
    const rows = await db
      .select()
      .from(ledgerTable)
      .where(
        and(
          eq(ledgerTable.tenantId, tenantId),
          eq(ledgerTable.userId, userId),
          eq(ledgerTable.resourceType, resourceType)
        )
      )
      .orderBy(asc(ledgerTable.createdAt));
    return rows.map(toDomain);
  }

  async getAllForTenant(tenantId: TenantId, resourceType?: ResourceType): Promise<LedgerEntry[]> {
    const db = getDb();
    const conditions = resourceType
      ? and(eq(ledgerTable.tenantId, tenantId), eq(ledgerTable.resourceType, resourceType))
      : eq(ledgerTable.tenantId, tenantId);
    const rows = await db.select().from(ledgerTable).where(conditions).orderBy(asc(ledgerTable.createdAt));
    return rows.map(toDomain);
  }
}

interface LedgerRow {
  id: string;
  tenantId: string;
  userId: string | null;
  resourceType: string;
  entryType: string;
  amount: number;
  balance: number;
  reason: string | null;
  createdAt: Date;
}

const toDomain = (row: LedgerRow): LedgerEntity =>
  new LedgerEntity({
    id: asLedgerId(row.id),
    tenantId: asTenantId(row.tenantId),
    userId: row.userId ? asUserId(row.userId) : undefined,
    resourceType: row.resourceType as ResourceType,
    entryType: row.entryType as LedgerEntryType,
    amount: asAmount(row.amount),
    balance: asAmount(row.balance),
    createdAt: row.createdAt,
    reason: row.reason ?? undefined,
  });
