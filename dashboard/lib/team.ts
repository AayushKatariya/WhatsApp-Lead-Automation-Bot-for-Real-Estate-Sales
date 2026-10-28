import type { Db, Role, User } from "./types";

export type TeamMember = { email: string; name: string; role: Role; site_ids: string[] };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const SITE_ID = /^[\w-]{1,40}$/;

/** "a@x.com, B@y.com" -> ["a@x.com", "b@y.com"] */
export function parseEmails(value: string): string[] {
  return [...new Set(value.split(/[\s,;]+/).map((e) => e.trim().toLowerCase()).filter((e) => EMAIL.test(e)))];
}

/**
 * Who this Google account is in the dashboard, or null if they may not sign in.
 * OWNER_EMAILS (from the settings) are always owners, so the owner can never lock themselves out.
 */
export async function findUser(db: Db, email: string, ownerEmails: string[]): Promise<User | null> {
  const key = email.trim().toLowerCase();
  const { rows } = await db.query<TeamMember>("SELECT email, name, role, site_ids FROM team WHERE email = $1", [key]);
  const row = rows[0];
  if (ownerEmails.includes(key)) return { email: key, name: row?.name ?? "", role: "owner", siteIds: [] };
  if (!row) return null;
  return { email: key, name: row.name, role: row.role, siteIds: row.site_ids };
}

export async function listTeam(db: Db): Promise<TeamMember[]> {
  const { rows } = await db.query<TeamMember>(
    "SELECT email, name, role, site_ids FROM team ORDER BY role, lower(name), email",
  );
  return rows;
}

export type MemberInput = { email: string; name: string; role: Role; siteIds: string[] };

/** Reads and checks the Team page form. */
export function parseMemberForm(form: FormData): MemberInput | { error: string } {
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  const name = String(form.get("name") ?? "").trim().slice(0, 100);
  const role = String(form.get("role") ?? "");
  const typed = String(form.get("other_sites") ?? "").split(/[\s,;]+/);
  const siteIds = [...new Set([...form.getAll("sites").map(String), ...typed].map((s) => s.trim()).filter(Boolean))];

  if (!EMAIL.test(email)) return { error: "Enter the Google email address they sign in with." };
  if (role !== "owner" && role !== "sales") return { error: "Choose Owner or Sales." };
  const bad = siteIds.find((s) => !SITE_ID.test(s));
  if (bad) return { error: `"${bad}" doesn't look like a site_id. Use the codes from the Sites tab, e.g. GV.` };
  if (role === "sales" && siteIds.length === 0) return { error: "Tick at least one project for a sales rep." };
  return { email, name, role, siteIds: role === "owner" ? [] : siteIds };
}

export async function saveMember(db: Db, m: MemberInput): Promise<void> {
  await db.query(
    `INSERT INTO team (email, name, role, site_ids) VALUES ($1, $2, $3, $4::text[])
     ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, role = EXCLUDED.role, site_ids = EXCLUDED.site_ids`,
    [m.email, m.name, m.role, m.siteIds],
  );
}

export async function removeMember(db: Db, email: string): Promise<void> {
  await db.query("DELETE FROM team WHERE email = $1", [email.trim().toLowerCase()]);
}
