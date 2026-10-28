// Shared by proxy.ts and the server code, so no server-only imports here.

export const SESSION_COOKIE = "lead_session";
export const OAUTH_COOKIE = "lead_oauth";

/** Only same-site paths, so a crafted sign-in link can't send people elsewhere. */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  return next;
}
