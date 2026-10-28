import "server-only";
import { parseEmails } from "./team";

// Read at request time, never at build time: Cloud Run passes these in when the server starts.
const read = (name: string) => (process.env[name] ?? "").trim();

export const env = {
  /** The dashboard's public address, e.g. https://lead-dashboard-abc123-el.a.run.app */
  appUrl: () => read("APP_URL").replace(/\/+$/, ""),
  googleClientId: () => read("GOOGLE_CLIENT_ID"),
  googleClientSecret: () => read("GOOGLE_CLIENT_SECRET"),
  sessionSecret: () => read("SESSION_SECRET"),
  /** Always owners, even if missing from the Team page */
  ownerEmails: () => parseEmails(read("OWNER_EMAILS")),
};
