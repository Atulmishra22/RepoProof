import { Pool } from 'pg';

const globalForDb = global as unknown as { db: Pool };

export const dbPool = globalForDb.db || new Pool({
  connectionString: process.env.DATABASE_URL,
});

if (process.env.NODE_ENV !== 'production') globalForDb.db = dbPool;
