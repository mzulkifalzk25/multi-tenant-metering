import { drizzle, type NodePgDatabase } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';
import { bigint, index, pgTable, text, timestamp, varchar } from 'drizzle-orm/pg-core';

/**
 * The immutable event log. Rows are only ever inserted, never updated or
 * deleted — that invariant is enforced at the repository layer, not here,
 * because Postgres itself has no portable "append-only table" primitive.
 */
export const ledgerTable = pgTable(
  'ledger',
  {
    id: varchar('id', { length: 255 }).primaryKey(),
    tenantId: varchar('tenant_id', { length: 255 }).notNull(),
    userId: varchar('user_id', { length: 255 }),
    resourceType: varchar('resource_type', { length: 50 }).notNull(),
    entryType: varchar('entry_type', { length: 50 }).notNull(),
    amount: bigint('amount', { mode: 'number' }).notNull(),
    balance: bigint('balance', { mode: 'number' }).notNull(),
    reason: text('reason'),
    createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => ({
    tenantIdx: index('ledger_tenant_idx').on(table.tenantId),
    // The hot query path: "give me every entry for this scope+resource, in order."
    scopeResourceIdx: index('ledger_scope_resource_idx').on(
      table.tenantId,
      table.userId,
      table.resourceType,
      table.createdAt
    ),
  })
);

/**
 * Materialized "current commitment" per scope+resource. Kept in sync by the
 * use cases whenever they append an `allocated`/`deallocated` ledger entry;
 * the ledger remains the source of truth if this ever needs to be rebuilt.
 */
export const allocationsTable = pgTable(
  'allocations',
  {
    id: varchar('id', { length: 255 }).primaryKey(),
    tenantId: varchar('tenant_id', { length: 255 }).notNull(),
    userId: varchar('user_id', { length: 255 }),
    resourceType: varchar('resource_type', { length: 50 }).notNull(),
    allocated: bigint('allocated', { mode: 'number' }).notNull(),
    createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => ({
    scopeResourceIdx: index('alloc_scope_resource_idx').on(table.tenantId, table.userId, table.resourceType),
  })
);

/** Materialized "actually spent" per scope+resource, kept in sync from `consumed` ledger entries. */
export const consumptionsTable = pgTable(
  'consumptions',
  {
    tenantId: varchar('tenant_id', { length: 255 }).notNull(),
    userId: varchar('user_id', { length: 255 }),
    resourceType: varchar('resource_type', { length: 50 }).notNull(),
    consumed: bigint('consumed', { mode: 'number' }).notNull(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow().notNull(),
  },
  (table) => ({
    scopeResourceIdx: index('consumption_scope_resource_idx').on(table.tenantId, table.userId, table.resourceType),
  })
);

/** The platform-level ceiling per resource type — the root of the allocation hierarchy. */
export const quotaPoolsTable = pgTable('quota_pools', {
  id: varchar('id', { length: 255 }).primaryKey(),
  resourceType: varchar('resource_type', { length: 50 }).notNull().unique(),
  capacity: bigint('capacity', { mode: 'number' }).notNull(),
  allocatedToTenants: bigint('allocated_to_tenants', { mode: 'number' }).notNull(),
});

let pool: Pool | undefined;
let db: NodePgDatabase | undefined;

/**
 * Lazily creates the shared connection pool and Drizzle instance. Lazy so
 * that importing this module (e.g. from a unit test that never touches the
 * database) never requires DATABASE_URL to be set.
 */
export const getDb = (): NodePgDatabase => {
  if (!db) {
    pool = new Pool({ connectionString: process.env['DATABASE_URL'] });
    db = drizzle(pool);
  }
  return db;
};

export const closeDb = async (): Promise<void> => {
  await pool?.end();
  pool = undefined;
  db = undefined;
};
