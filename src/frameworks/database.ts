import { drizzle, type NodePgDatabase } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';

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
