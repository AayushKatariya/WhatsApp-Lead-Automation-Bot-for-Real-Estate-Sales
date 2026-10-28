"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE } from "@/lib/cookies";

export async function signOut() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}
