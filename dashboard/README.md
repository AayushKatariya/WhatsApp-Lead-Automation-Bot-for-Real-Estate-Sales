# Lead dashboard

A small Next.js app where owners and sales reps read every WhatsApp lead's full conversation with the bot. The bot (`../history.py`) writes each message, delivery update and lead event to PostgreSQL. This app reads them, with Google sign-in and per-project access.

- **Stack:** Next.js 16 (App Router, Cache Components), React 19, Tailwind CSS 4, `pg`, `jose`; PostgreSQL on Neon; Google Cloud Run (`asia-south1`)
- **Deploy:** see [Deploy (Cloud Run)](#deploy-cloud-run) below

## Pages

| Path | What it shows | Who |
| --- | --- | --- |
| `/` | Leads, newest first: search (name, number, message text), project filter, "needs follow-up" | Owners: all leads. Sales: leads with an event for one of their projects |
| `/leads/[phone]` | The whole conversation: menus, brochures, buttons, pins, contact cards, delivery ticks, failures with Meta's reason, and notes for lead events | Same rule; other leads are "not found" |
| `/team` | Add, edit, remove people; pick each rep's projects | Owners only |
| `/login`, `/auth/google`, `/auth/callback` | Google sign-in (OAuth code flow with PKCE) | Everyone |

**Live updates.** The leads list and conversation pages update themselves every 10 seconds (`components/live.tsx`, `router.refresh()`), keeping scroll position and half-typed filters. Checking pauses while the tab is hidden and after 15 minutes without mouse, keyboard or touch, so Neon's free database can go to sleep; coming back updates at once. A conversation scrolls to new messages only if the reader is already at the bottom. If a background update fails, the error page (`app/(app)/error.tsx`) calls `retry()` every 10 seconds until the page loads again.

## How access works

1. `/auth/callback` verifies Google's ID token (signature, issuer, audience, expiry, verified email) and lets in only emails on the `team` table or in `OWNER_EMAILS`.
2. The session is an encrypted cookie (`jose`, A256GCM, 30 days) holding the email.
3. Every page and server action calls `getCurrentUser()` (`lib/auth.ts`), which looks the email up again. Removing someone or changing their projects takes effect on their next click.
4. Rep limits are applied in SQL (`scope()` in `lib/leads.ts`), so URL tricks can't widen them.
5. `proxy.ts` only does a quick "has a cookie?" redirect to `/login`. It isn't the security check.

## Code map

| Path | Responsibility |
| --- | --- |
| `db/schema.sql` | All tables. Applied automatically on first database use (`lib/db.ts`, under an advisory lock). Additive changes only |
| `lib/leads.ts` | Lead list, project list, one lead, timeline. Every query takes the `Db` and the `User` |
| `lib/team.ts` | Team table, `findUser`, Team form validation |
| `lib/auth.ts` | `getCurrentUser()` / `requireOwner()`: the data-access check |
| `lib/session.ts`, `lib/google.ts` | Encrypted session cookie; Google OAuth and ID-token checks |
| `lib/format.ts` | India time, phone numbers, event labels, WhatsApp `*bold*` |
| `components/message.tsx` | Renders each stored WhatsApp payload as a chat bubble |
| `components/live.tsx` | `LiveRefresh` (the "Live" badge that keeps pages fresh) and `FollowLatest` (scrolls to new messages) |
| `tests/` | Vitest. Queries run against PGlite (real Postgres in memory) with `db/schema.sql` |

## Settings (environment variables)

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | Postgres connection string (Neon; the bot uses the same one) |
| `APP_URL` | The dashboard's public address, no trailing `/`; Google redirects to `APP_URL/auth/callback` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth web client from Google Cloud |
| `SESSION_SECRET` | 32+ characters; changing it signs everyone out |
| `OWNER_EMAILS` | Comma-separated; always owners (so the owner can't lock themselves out) |

On Cloud Run they come from `env.yaml` (copy `env.yaml.example`; gitignored and gcloudignored). Locally, put them in `.env.local`.

## Develop

```bash
npm install
npm run db:dev        # local Postgres (PGlite) on 127.0.0.1:5432, data kept in .pglite/; leave running
# in another terminal, from the repo root: sample conversations made by the real bot code
DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres python tools/demo_conversations.py
npm run dev           # http://localhost:3000
```

`.env.local` for development: `DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres`, `APP_URL=http://localhost:3000`, a `SESSION_SECRET`, your email in `OWNER_EMAILS`, and a Google OAuth client with the redirect URI `http://localhost:3000/auth/callback`.

```bash
npm test              # vitest: queries on PGlite, auth, formatting
npm run typecheck     # route types + tsc
npm run lint
npm run build         # standalone server in .next/standalone (what the Dockerfile ships)
```

**After adding or updating packages on Windows or macOS,** check the lockfile also works on Linux (Cloud Build). npm sometimes leaves out packages that only other platforms need, and `npm ci` in the Docker build then fails with "Missing: … from lock file":

```bash
npx npm@11 ci --dry-run --ignore-scripts --os=linux --cpu=x64 --libc=glibc   # must end without "npm error"
npx npm@11 install --package-lock-only --ignore-scripts                      # repairs the lockfile if it doesn't
```

**Next.js 16 notes:** `cacheComponents` is on. Anything that reads cookies, search params or the database sits inside a `<Suspense>` boundary, and the page shell outside it is prerendered. No data is cached (`use cache` isn't used), so leads are always fresh. This version differs from older Next.js; read the guides in `node_modules/next/dist/docs/` before changing framework-level code (see `AGENTS.md`).

## Deploy (Cloud Run)

```bash
gcloud iam service-accounts create lead-dashboard --display-name="Lead dashboard"   # once; it needs no roles
gcloud run deploy lead-dashboard --source dashboard --region asia-south1 --allow-unauthenticated \
  --service-account "lead-dashboard@$(gcloud config get-value project).iam.gserviceaccount.com" \
  --env-vars-file dashboard/env.yaml
gcloud run services update lead-dashboard --region asia-south1 --env-vars-file dashboard/env.yaml   # settings only
```

`--allow-unauthenticated` lets browsers reach the sign-in page; the app does its own sign-in check.
