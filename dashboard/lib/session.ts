import { createHash } from "node:crypto";
import { EncryptJWT, jwtDecrypt } from "jose";

export type Session = { email: string; name: string };

export const SESSION_DAYS = 30;

/** The cookie is encrypted, not just signed, so it doesn't reveal the email inside. */
function key(secret: string): Uint8Array {
  if (secret.length < 32) throw new Error("SESSION_SECRET must be at least 32 characters");
  return createHash("sha256").update(secret).digest();
}

export async function sealSession(session: Session, secret: string): Promise<string> {
  return new EncryptJWT({ email: session.email, name: session.name })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt()
    .setExpirationTime(`${SESSION_DAYS}d`)
    .encrypt(key(secret));
}

/** The session in the cookie, or null if it's missing, tampered with or expired. */
export async function openSession(token: string | undefined, secret: string): Promise<Session | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtDecrypt(token, key(secret), {
      keyManagementAlgorithms: ["dir"],
      contentEncryptionAlgorithms: ["A256GCM"],
    });
    if (typeof payload.email !== "string") return null;
    return { email: payload.email, name: typeof payload.name === "string" ? payload.name : "" };
  } catch {
    return null;
  }
}

export const sessionCookieOptions = {
  httpOnly: true,
  secure: true, // browsers accept Secure cookies on http://localhost too
  sameSite: "lax" as const,
  path: "/",
  maxAge: SESSION_DAYS * 24 * 3600,
};
