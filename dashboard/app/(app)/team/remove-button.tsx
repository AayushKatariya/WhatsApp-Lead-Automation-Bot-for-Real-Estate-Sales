"use client";

import { removeMemberAction } from "./actions";

export function RemoveButton({ email }: { email: string }) {
  return (
    <form
      action={removeMemberAction}
      onSubmit={(e) => {
        if (!confirm(`Remove ${email}? They won't be able to sign in any more.`)) e.preventDefault();
      }}
    >
      <input type="hidden" name="email" value={email} />
      <button className="rounded-md px-2 py-1 text-sm text-danger hover:bg-danger-soft">Remove</button>
    </form>
  );
}
