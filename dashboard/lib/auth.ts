import "server-only";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { cache } from "react";
import { SESSION_COOKIE } from "./cookies";
import { getDb } from "./db";
import { env } from "./env";
import { openSession } from "./session";
import { findUser } from "./team";
import type { User } from "./types";

/**
 * The signed-in user, checked against the Team list on every request, so removing
 * someone or changing their projects takes effect immediately. Redirects to /login otherwise.
 */
export const getCurrentUser = cache(async (): Promise<User> => {
  const session = await openSession((await cookies()).get(SESSION_COOKIE)?.value, env.sessionSecret());
  if (!session) redirect("/login");
  const user = await findUser(await getDb(), session.email, env.ownerEmails());
  if (!user) redirect("/login?error=removed");
  return { ...user, name: user.name || session.name };
});

/** For owner-only pages and actions: everyone else gets "not found". */
export async function requireOwner(): Promise<User> {
  const user = await getCurrentUser();
  if (user.role !== "owner") notFound();
  return user;
}
