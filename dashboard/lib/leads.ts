import type { Db, Project, User } from "./types";

/** Events that mean a person should follow up. */
export const FOLLOW_UP_EVENTS = ["visit_request", "sales_request", "price_request", "handoff", "non_text"];
export const PAGE_SIZE = 50;

export type LeadFilters = { q?: string; site?: string; followUp?: boolean; page?: number };

export type LeadSummary = {
  phone: string;
  name: string;
  first_seen: Date;
  last_seen: Date;
  sites: string[];
  events: string[];
  last_body: string | null;
  last_kind: string | null;
  last_direction: "in" | "out" | null;
};

export type Lead = { phone: string; name: string; first_seen: Date; last_seen: Date; sites: string[] };

export type Message = {
  id: string;
  direction: "in" | "out";
  kind: string;
  body: string;
  payload: Record<string, unknown> | unknown[];
  status: string;
  error: string;
  created_at: Date;
};

export type LeadEvent = {
  id: string;
  site_id: string;
  site_name: string;
  event: string;
  detail: string;
  created_at: Date;
};

export type TimelineItem = ({ type: "message" } & Message) | ({ type: "event" } & LeadEvent);

class Params {
  values: unknown[] = [];
  add(value: unknown): string {
    this.values.push(value);
    return `$${this.values.length}`;
  }
}

/** SQL that limits contacts (alias c) to what this user may see: a sales rep only leads who enquired about their projects. */
function scope(user: User, p: Params): string | null {
  if (user.role === "owner") return null;
  return `EXISTS (SELECT 1 FROM events e WHERE e.phone = c.phone AND e.site_id = ANY(${p.add(user.siteIds)}::text[]))`;
}

function escapeLike(text: string): string {
  return text.replace(/[\\%_]/g, "\\$&");
}

export async function listLeads(db: Db, user: User, filters: LeadFilters) {
  const p = new Params();
  const where: string[] = [];
  const own = scope(user, p);
  if (own) where.push(own);
  if (filters.site) {
    where.push(`EXISTS (SELECT 1 FROM events e WHERE e.phone = c.phone AND e.site_id = ${p.add(filters.site)})`);
  }
  if (filters.followUp) {
    where.push(
      `EXISTS (SELECT 1 FROM events e WHERE e.phone = c.phone AND e.event = ANY(${p.add(FOLLOW_UP_EVENTS)}::text[]))`,
    );
  }
  const q = filters.q?.trim();
  if (q) {
    const like = p.add(`%${escapeLike(q)}%`);
    const either = [
      `c.name ILIKE ${like}`,
      `EXISTS (SELECT 1 FROM messages m WHERE m.phone = c.phone AND m.body ILIKE ${like})`,
    ];
    const digits = q.replace(/\D/g, "");
    if (digits.length >= 4) either.push(`c.phone LIKE ${p.add(`%${digits}%`)}`);
    where.push(`(${either.join(" OR ")})`);
  }
  const page = Math.max(1, Math.floor(filters.page ?? 1));
  const { rows } = await db.query<LeadSummary>(
    `SELECT c.phone, c.name, c.first_seen, c.last_seen,
            COALESCE(ev.sites, '{}') AS sites, COALESCE(ev.events, '{}') AS events,
            lm.body AS last_body, lm.kind AS last_kind, lm.direction AS last_direction
     FROM contacts c
     LEFT JOIN LATERAL (
       SELECT array_agg(DISTINCT e.site_name) FILTER (WHERE e.site_id <> '') AS sites,
              array_agg(DISTINCT e.event) AS events
       FROM events e WHERE e.phone = c.phone
     ) ev ON true
     LEFT JOIN LATERAL (
       SELECT m.body, m.kind, m.direction FROM messages m
       WHERE m.phone = c.phone ORDER BY m.created_at DESC, m.id DESC LIMIT 1
     ) lm ON true
     ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
     ORDER BY c.last_seen DESC, c.phone
     LIMIT ${p.add(PAGE_SIZE + 1)} OFFSET ${p.add((page - 1) * PAGE_SIZE)}`,
    p.values,
  );
  return { leads: rows.slice(0, PAGE_SIZE), hasMore: rows.length > PAGE_SIZE, page };
}

/** The projects this user can filter by: those that have had enquiries (owners: all; reps: theirs). */
export async function listProjects(db: Db, user: User): Promise<Project[]> {
  const p = new Params();
  const mine = user.role === "owner" ? "" : `AND site_id = ANY(${p.add(user.siteIds)}::text[])`;
  const { rows } = await db.query<Project>(
    `SELECT DISTINCT ON (site_id) site_id, site_name FROM events
     WHERE site_id <> '' ${mine}
     ORDER BY site_id, created_at DESC`,
    p.values,
  );
  return rows.sort((a, b) => a.site_name.localeCompare(b.site_name));
}

/** One lead, or null if it doesn't exist or this user may not see it. */
export async function getLead(db: Db, user: User, phone: string): Promise<Lead | null> {
  const p = new Params();
  const where = [`c.phone = ${p.add(phone)}`];
  const own = scope(user, p);
  if (own) where.push(own);
  const { rows } = await db.query<Lead>(
    `SELECT c.phone, c.name, c.first_seen, c.last_seen,
            COALESCE((SELECT array_agg(DISTINCT e.site_name) FROM events e
                      WHERE e.phone = c.phone AND e.site_id <> ''), '{}') AS sites
     FROM contacts c WHERE ${where.join(" AND ")}`,
    p.values,
  );
  return rows[0] ?? null;
}

/** Messages and events for one lead, in the order they happened. Call only after getLead() allowed it. */
export async function getTimeline(db: Db, phone: string): Promise<TimelineItem[]> {
  const [messages, events] = await Promise.all([
    db.query<Message>(
      `SELECT id::text, direction, kind, body, payload, status, error, created_at FROM messages
       WHERE phone = $1 ORDER BY created_at, id LIMIT 5000`,
      [phone],
    ),
    db.query<LeadEvent>(
      `SELECT id::text, site_id, site_name, event, detail, created_at FROM events
       WHERE phone = $1 ORDER BY created_at, id LIMIT 5000`,
      [phone],
    ),
  ]);
  const items: TimelineItem[] = [
    ...messages.rows.map((m) => ({ type: "message" as const, ...m })),
    ...events.rows.map((e) => ({ type: "event" as const, ...e })),
  ];
  // messages and events share one id counter (db/schema.sql): ids give the exact order they were saved
  return items.sort((a, b) => Number(a.id) - Number(b.id));
}
