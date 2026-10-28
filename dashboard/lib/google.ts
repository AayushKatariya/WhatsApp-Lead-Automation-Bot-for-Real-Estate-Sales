// "Sign in with Google": the OAuth 2.0 authorization-code flow with PKCE.
import { createHash, randomBytes } from "node:crypto";
import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";

const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const ISSUERS = ["https://accounts.google.com", "accounts.google.com"];
const googleKeys = createRemoteJWKSet(new URL("https://www.googleapis.com/oauth2/v3/certs"));

export function randomToken(): string {
  return randomBytes(32).toString("base64url");
}

export function authorizationUrl(opts: { clientId: string; redirectUri: string; state: string; verifier: string }) {
  const url = new URL(AUTH_URL);
  url.search = new URLSearchParams({
    client_id: opts.clientId,
    redirect_uri: opts.redirectUri,
    response_type: "code",
    scope: "openid email profile",
    state: opts.state,
    code_challenge: createHash("sha256").update(opts.verifier).digest("base64url"),
    code_challenge_method: "S256",
    prompt: "select_account",
  }).toString();
  return url.toString();
}

/** Swaps the code Google sent back for an ID token. */
export async function exchangeCode(
  opts: { code: string; verifier: string; clientId: string; clientSecret: string; redirectUri: string },
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const res = await fetchImpl(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code: opts.code,
      code_verifier: opts.verifier,
      client_id: opts.clientId,
      client_secret: opts.clientSecret,
      redirect_uri: opts.redirectUri,
    }),
  });
  const data = (await res.json().catch(() => ({}))) as { id_token?: unknown; error?: unknown };
  if (!res.ok || typeof data.id_token !== "string") {
    throw new Error(`Google token exchange failed (${res.status} ${String(data.error ?? "")})`);
  }
  return data.id_token;
}

/** Checks Google's signature, issuer, audience and expiry; returns the verified email. */
export async function verifyIdToken(idToken: string, clientId: string, keys: JWTVerifyGetKey = googleKeys) {
  const { payload } = await jwtVerify(idToken, keys, { issuer: ISSUERS, audience: clientId });
  if (payload.email_verified !== true || typeof payload.email !== "string") {
    throw new Error("The Google account's email isn't verified");
  }
  return { email: payload.email.toLowerCase(), name: typeof payload.name === "string" ? payload.name : "" };
}
