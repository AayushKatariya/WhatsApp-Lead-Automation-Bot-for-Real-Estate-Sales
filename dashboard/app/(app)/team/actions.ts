"use server";

import { refresh } from "next/cache";
import { getCurrentUser } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { parseMemberForm, removeMember, saveMember } from "@/lib/team";

export type SaveState = { ok?: string; error?: string; nonce?: number };

// Every action checks the signed-in user itself: a form can be posted by anyone.

export async function saveMemberAction(_prev: SaveState, form: FormData): Promise<SaveState> {
  const me = await getCurrentUser();
  if (me.role !== "owner") return { error: "Only owners can change the team." };
  const input = parseMemberForm(form);
  if ("error" in input) return { error: input.error };
  if (input.email === me.email && input.role !== "owner") {
    return { error: "You can't remove your own owner access. Ask another owner." };
  }
  await saveMember(await getDb(), input);
  refresh();
  return { ok: `Saved ${input.email}.`, nonce: Date.now() };
}

export async function removeMemberAction(form: FormData): Promise<void> {
  const me = await getCurrentUser();
  if (me.role !== "owner") return;
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  if (!email || email === me.email) return; // never lock yourself out
  await removeMember(await getDb(), email);
  refresh();
}
