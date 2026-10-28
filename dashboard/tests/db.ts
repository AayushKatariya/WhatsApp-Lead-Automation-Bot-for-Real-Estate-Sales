// A real PostgreSQL (PGlite, in memory) with the dashboard's schema, plus helpers to add data.
import { readFileSync } from "node:fs";
import { PGlite } from "@electric-sql/pglite";
import type { Db } from "@/lib/types";

export async function testDb(): Promise<PGlite & Db> {
  const db = new PGlite();
  await db.exec(readFileSync(new URL("../db/schema.sql", import.meta.url), "utf8"));
  return db as PGlite & Db;
}

export async function reset(db: PGlite) {
  await db.exec("TRUNCATE contacts, messages, events, team RESTART IDENTITY");
}

let clock = Date.parse("2026-10-27T05:00:00Z");
const tick = () => new Date((clock += 60_000)).toISOString();

export async function contact(db: PGlite, phone: string, name: string) {
  const at = tick();
  await db.query("INSERT INTO contacts (phone, name, first_seen, last_seen) VALUES ($1, $2, $3, $3)", [phone, name, at]);
}

export async function message(db: PGlite, phone: string, direction: "in" | "out", kind: string, body: string, payload = {}) {
  const at = tick();
  await db.query(
    "INSERT INTO messages (phone, direction, kind, body, payload, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
    [phone, direction, kind, body, JSON.stringify(payload), at],
  );
  if (direction === "in") await db.query("UPDATE contacts SET last_seen = $2 WHERE phone = $1", [phone, at]);
}

export async function event(db: PGlite, phone: string, event: string, site: [string, string] | null, detail = "") {
  await db.query(
    "INSERT INTO events (phone, site_id, site_name, event, detail, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
    [phone, site?.[0] ?? "", site?.[1] ?? "", event, detail, tick()],
  );
}
