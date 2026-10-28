import { createHash } from "node:crypto";
import { createLocalJWKSet, EncryptJWT, exportJWK, generateKeyPair, SignJWT } from "jose";
import { expect, it } from "vitest";
import { safeNext } from "@/lib/cookies";
import { authorizationUrl, exchangeCode, verifyIdToken } from "@/lib/google";
import { openSession, sealSession } from "@/lib/session";

const SECRET = "a-long-random-session-secret-of-at-least-32-chars";

it("seals and opens a session; tampered, foreign or expired cookies are rejected", async () => {
  const token = await sealSession({ email: "rahul@gmail.com", name: "Rahul" }, SECRET);
  expect(token).not.toContain("rahul"); // encrypted, not just signed
  expect(await openSession(token, SECRET)).toEqual({ email: "rahul@gmail.com", name: "Rahul" });
  expect(await openSession(token.slice(0, -2) + "xx", SECRET)).toBeNull();
  expect(await openSession(token, "another-secret-that-is-also-long-enough")).toBeNull();
  expect(await openSession(undefined, SECRET)).toBeNull();

  const expired = await new EncryptJWT({ email: "rahul@gmail.com" })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setExpirationTime(Math.floor(Date.now() / 1000) - 60)
    .encrypt(createHash("sha256").update(SECRET).digest());
  expect(await openSession(expired, SECRET)).toBeNull();
  await expect(sealSession({ email: "a@b.co", name: "" }, "short")).rejects.toThrow("SESSION_SECRET");
});

it("only follows same-site paths after sign-in", () => {
  expect(safeNext("/leads/919800000001?x=1")).toBe("/leads/919800000001?x=1");
  for (const bad of ["https://evil.com", "//evil.com", "/\\evil.com", "", null]) expect(safeNext(bad)).toBe("/");
});

it("builds Google's sign-in address with PKCE", () => {
  const url = new URL(authorizationUrl({ clientId: "cid", redirectUri: "https://d.run.app/auth/callback", state: "s1", verifier: "v1" }));
  expect(url.origin + url.pathname).toBe("https://accounts.google.com/o/oauth2/v2/auth");
  expect(Object.fromEntries(url.searchParams)).toMatchObject({
    client_id: "cid",
    redirect_uri: "https://d.run.app/auth/callback",
    scope: "openid email profile",
    state: "s1",
    code_challenge: createHash("sha256").update("v1").digest("base64url"),
    code_challenge_method: "S256",
  });
});

it("exchanges the code for an ID token", async () => {
  const sent: URLSearchParams[] = [];
  const ok = (async (_url: string, init: RequestInit) => {
    sent.push(init.body as URLSearchParams);
    return Response.json({ id_token: "token123" });
  }) as typeof fetch;
  const opts = { code: "c", verifier: "v", clientId: "cid", clientSecret: "sec", redirectUri: "https://d/auth/callback" };
  expect(await exchangeCode(opts, ok)).toBe("token123");
  expect(sent[0].get("code_verifier")).toBe("v");
  const refused = (async () => Response.json({ error: "invalid_grant" }, { status: 400 })) as typeof fetch;
  await expect(exchangeCode(opts, refused)).rejects.toThrow("invalid_grant");
});

it("accepts only Google-signed tokens for this app with a verified email", async () => {
  const { privateKey, publicKey } = await generateKeyPair("RS256");
  const keys = createLocalJWKSet({ keys: [{ ...(await exportJWK(publicKey)), kid: "k1", alg: "RS256" }] });
  const token = (claims: Record<string, unknown>, aud = "cid", iss = "https://accounts.google.com") =>
    new SignJWT(claims)
      .setProtectedHeader({ alg: "RS256", kid: "k1" })
      .setIssuer(iss)
      .setAudience(aud)
      .setExpirationTime("5m")
      .sign(privateKey);

  const good = await token({ email: "Rahul@Gmail.com", email_verified: true, name: "Rahul" });
  expect(await verifyIdToken(good, "cid", keys)).toEqual({ email: "rahul@gmail.com", name: "Rahul" });
  await expect(verifyIdToken(good, "another-app", keys)).rejects.toThrow();
  await expect(verifyIdToken(await token({ email: "a@b.co", email_verified: true }, "cid", "https://evil.com"), "cid", keys)).rejects.toThrow();
  await expect(verifyIdToken(await token({ email: "a@b.co", email_verified: false }), "cid", keys)).rejects.toThrow("verified");
});
