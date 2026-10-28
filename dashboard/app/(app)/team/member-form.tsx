"use client";

import { startTransition, useActionState, useState } from "react";
import { inputClass, primaryButton } from "@/components/ui";
import type { TeamMember } from "@/lib/team";
import type { Project } from "@/lib/types";
import { saveMemberAction, type SaveState } from "./actions";

/** Add a person (member = undefined) or edit one. */
export function MemberForm({ member, projects }: { member?: TeamMember; projects: Project[] }) {
  const [state, action, pending] = useActionState<SaveState, FormData>(saveMemberAction, {});
  const [role, setRole] = useState(member?.role ?? "sales");
  const known = new Set(projects.map((p) => p.site_id));
  const otherSites = (member?.site_ids ?? []).filter((s) => !known.has(s)).join(", ");

  return (
    // Submitted by hand so a validation error keeps what was typed (a form action would clear it).
    // A new nonce after a successful save resets the "add" form to empty.
    <form
      key={member ? member.email : state.nonce}
      onSubmit={(e) => {
        e.preventDefault();
        const data = new FormData(e.currentTarget);
        startTransition(() => action(data));
      }}
      className="space-y-4"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Google email</span>
          {member ? (
            <>
              <input type="hidden" name="email" value={member.email} />
              <span className="block py-2 text-muted">{member.email}</span>
            </>
          ) : (
            <input name="email" type="email" required placeholder="rahul@gmail.com" className={inputClass} />
          )}
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Name</span>
          <input name="name" defaultValue={member?.name} placeholder="Rahul Patil" className={inputClass} />
        </label>
      </div>

      <fieldset className="text-sm">
        <legend className="mb-1 font-medium">Role</legend>
        <div className="flex flex-wrap gap-4">
          {(["sales", "owner"] as const).map((r) => (
            <label key={r} className="flex items-center gap-2">
              <input
                type="radio"
                name="role"
                value={r}
                checked={role === r}
                onChange={() => setRole(r)}
                className="accent-accent"
              />
              {r === "owner" ? "Owner: sees every lead, manages the team" : "Sales: sees only their projects"}
            </label>
          ))}
        </div>
      </fieldset>

      {role === "sales" && (
        <fieldset className="text-sm">
          <legend className="mb-1 font-medium">Projects</legend>
          {projects.length > 0 ? (
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {projects.map((p) => (
                <label key={p.site_id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    name="sites"
                    value={p.site_id}
                    defaultChecked={member?.site_ids.includes(p.site_id)}
                    className="accent-accent"
                  />
                  {p.site_name || p.site_id} <span className="text-muted">({p.site_id})</span>
                </label>
              ))}
            </div>
          ) : (
            <p className="text-muted">Projects appear here after their first enquiry.</p>
          )}
          <label className="mt-3 block">
            <span className="mb-1 block text-muted">Other site IDs from the Sheet&apos;s Sites tab, comma-separated</span>
            <input name="other_sites" defaultValue={otherSites} placeholder="GV, SH" className={`${inputClass} max-w-xs`} />
          </label>
        </fieldset>
      )}

      <div className="flex items-center gap-3">
        <button type="submit" disabled={pending} className={primaryButton}>
          {pending ? "Saving…" : member ? "Save changes" : "Add to team"}
        </button>
        {state.error && (
          <p role="alert" className="text-sm text-danger">
            {state.error}
          </p>
        )}
        {state.ok && <p className="text-sm text-accent">{state.ok}</p>}
      </div>
    </form>
  );
}
