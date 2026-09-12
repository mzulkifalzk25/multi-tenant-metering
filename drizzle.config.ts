import type { Config } from 'drizzle-kit';

export default {
  schema: './src/frameworks/database.ts',
  out: './drizzle',
  driver: 'pg',
  dbCredentials: {
    connectionString: process.env['DATABASE_URL'] ?? 'postgresql://metering:metering@localhost:5544/metering',
  },
} satisfies Config;
