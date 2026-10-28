import "server-only";
import { readFileSync } from "node:fs";
import path from "node:path";
import { Pool } from "pg";
import type { Db } from "./types";

const globalForDb = globalThis as unknown as { leadDb?: Promise<Db> };

/** The database, with the tables created on first use. */
export function getDb(): Promise<Db> {
  globalForDb.leadDb ??= connect().catch((error) => {
    globalForDb.leadDb = undefined; // try again on the next request
    throw error;
  });
  return globalForDb.leadDb;
}

async function connect(): Promise<Db> {
  const connectionString = (process.env.DATABASE_URL ?? "").trim();
  if (!connectionString) throw new Error("DATABASE_URL is not set");
  const pool = new Pool({ connectionString, max: 5, idleTimeoutMillis: 60_000 });
  // Neon closes idle connections when it sleeps; without this handler that would crash the server
  pool.on("error", (error) => console.error("Database connection dropped:", error.message));

  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query("SELECT pg_advisory_xact_lock(727274)"); // one server at a time
    await client.query(readFileSync(path.join(process.cwd(), "db", "schema.sql"), "utf8"));
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK").catch(() => {});
    throw error;
  } finally {
    client.release();
  }
  return { query: (text, params) => pool.query(text, params) as never };
}
