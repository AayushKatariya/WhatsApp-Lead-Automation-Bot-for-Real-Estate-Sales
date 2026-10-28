import { NextResponse, type NextRequest } from "next/server";
import { OAUTH_COOKIE, safeNext } from "@/lib/cookies";
import { env } from "@/lib/env";
import { authorizationUrl, randomToken } from "@/lib/google";

/** "Sign in with Google": remember a one-time state and PKCE verifier, then go to Google. */
export async function GET(request: NextRequest) {
  const appUrl = env.appUrl() || request.nextUrl.origin;
  const clientId = env.googleClientId();
  if (!clientId) return NextResponse.redirect(new URL("/login?error=setup", appUrl));

  const state = randomToken();
  const verifier = randomToken();
  const next = safeNext(request.nextUrl.searchParams.get("next"));
  const response = NextResponse.redirect(
    authorizationUrl({ clientId, redirectUri: `${appUrl}/auth/callback`, state, verifier }),
  );
  response.cookies.set(OAUTH_COOKIE, JSON.stringify({ state, verifier, next }), {
    httpOnly: true,
    secure: true,
    sameSite: "lax", // sent back when Google redirects to /auth/callback
    path: "/auth",
    maxAge: 600,
  });
  return response;
}
