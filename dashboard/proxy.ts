import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/cookies";

/**
 * A quick first check: without a session cookie, go straight to the sign-in page.
 * The real check (valid session, still on the team) happens on every page in lib/auth.ts.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const login = new URL("/login", process.env.APP_URL || request.url);
  const next = request.nextUrl.pathname + request.nextUrl.search;
  if (next !== "/") login.searchParams.set("next", next);
  return NextResponse.redirect(login);
}

export const config = {
  // everything except the sign-in pages, Next.js files and files with an extension (favicon etc.)
  matcher: ["/((?!login|auth/|_next/|.*\\..*).*)"],
};
