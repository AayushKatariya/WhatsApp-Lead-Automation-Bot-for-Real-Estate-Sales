import type { Metadata } from "next";
import { Suspense } from "react";
import { Badge, Skeleton } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { env } from "@/lib/env";
import { listProjects } from "@/lib/leads";
import { listTeam } from "@/lib/team";
import { MemberForm } from "./member-form";
import { RemoveButton } from "./remove-button";

export const metadata: Metadata = { title: "Team" };

export default function TeamPage() {
  return (
    <>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold tracking-tight">Team</h1>
        <p className="text-sm text-muted">
          Who can sign in. Owners see every lead; sales reps see only leads who enquired about their projects.
        </p>
      </div>
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <Team />
      </Suspense>
    </>
  );
}

async function Team() {
  const me = await requireOwner();
  const db = await getDb();
  const [members, projects] = await Promise.all([listTeam(db), listProjects(db, me)]);
  const fixedOwners = env.ownerEmails();
  const names = new Map(projects.map((p) => [p.site_id, p.site_name]));

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <h2 className="mb-4 font-semibold">Add someone</h2>
        <MemberForm projects={projects} />
      </section>

      <section className="overflow-hidden rounded-xl border border-line bg-surface">
        <ul className="divide-y divide-line">
          {fixedOwners
            .filter((email) => !members.some((m) => m.email === email))
            .map((email) => (
              <li key={email} className="flex flex-wrap items-center gap-2 px-4 py-3 text-sm">
                <span className="font-medium">{email}</span>
                <Badge>Owner</Badge>
                <span className="ml-auto text-xs text-muted">Set in the dashboard&apos;s settings (OWNER_EMAILS)</span>
              </li>
            ))}
          {members.map((m) => (
            <li key={m.email} className="px-4 py-3">
              <details className="group">
                <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">{m.name || m.email}</span>
                  {m.name && <span className="text-muted">{m.email}</span>}
                  <Badge tone={m.role === "owner" ? "neutral" : "accent"}>{m.role === "owner" ? "Owner" : "Sales"}</Badge>
                  {m.role === "sales" && (
                    <span className="text-xs text-muted">
                      {m.site_ids.map((id) => names.get(id) || id).join(", ") || "no projects"}
                    </span>
                  )}
                  <span className="ml-auto text-xs font-medium text-accent group-open:hidden">Edit</span>
                </summary>
                <div className="mt-4 border-t border-line pt-4">
                  <MemberForm member={m} projects={projects} />
                  {m.email !== me.email && !fixedOwners.includes(m.email) && (
                    <div className="mt-3 flex justify-end">
                      <RemoveButton email={m.email} />
                    </div>
                  )}
                </div>
              </details>
            </li>
          ))}
          {members.length === 0 && fixedOwners.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-muted">Nobody added yet.</li>
          )}
        </ul>
      </section>
    </div>
  );
}
