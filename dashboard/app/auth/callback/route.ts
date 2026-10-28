import { NextResponse, type NextRequest } from "next/server";
import { OAUTH_COOKIE, safeNext, SESSION_COOKIE } from "@/lib/cookies";
import { getDb } from "@/lib/db";
import { env } from "@/lib/env";
import { exchangeCode, verifyIdToken } from "@/lib/google";
import { sealSession, sessionCookieOptions } from "@/lib/session";
import { findUser } from "@/lib/team";

type Pending = { state: string; verifier: string; next: string };

function readPending(value: string | undefined): Pending | null {
  try {
    const parsed = JSON.parse(value ?? "");
    return typeof parsed?.state === "string" && typeof parsed?.verifier === "string" ? parsed : null;
  } catch {
    return null;
  }
}

/** Google sends people back here. Only emails on the Team list (or OWNER_EMAILS) get a session. */
export async function GET(request: NextRequest) {
  const appUrl = env.appUrl() || request.nextUrl.origin;
  const params = request.nextUrl.searchParams;
  const pending = readPending(request.cookies.get(OAUTH_COOKIE)?.value);

  const finish = (path: string) => {
    const response = NextResponse.redirect(new URL(path, appUrl));
    response.cookies.set(OAUTH_COOKIE, "", { path: "/auth", maxAge: 0 });
    return response;
  };

  if (params.get("error")) return finish("/login?error=cancelled");
  const code = params.get("code");
  if (!pending || !code || params.get("state") !== pending.state) return finish("/login?error=expired");

  let identity: { email: string; name: string };
  try {
    const clientId = env.googleClientId();
    const idToken = await exchangeCode({
      code,
      verifier: pending.verifier,
      clientId,
      clientSecret: env.googleClientSecret(),
      redirectUri: `${appUrl}/auth/callback`,
    });
    identity = await verifyIdToken(idToken, clientId);
  } catch (error) {
    console.error("Google sign-in failed:", error);
    return finish("/login?error=google");
  }

  const user = await findUser(await getDb(), identity.email, env.ownerEmails());
  if (!user) {
    console.warn("Sign-in refused: %s is not on the team list", identity.email);
    return finish("/login?error=not_allowed");
  }
  const response = finish(safeNext(pending.next));
  response.cookies.set(SESSION_COOKIE, await sealSession(identity, env.sessionSecret()), sessionCookieOptions);
  return response;
}
