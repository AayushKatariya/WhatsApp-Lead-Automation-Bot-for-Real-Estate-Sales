import type { Metadata } from "next";
import { Suspense } from "react";
import { safeNext } from "@/lib/cookies";

export const metadata: Metadata = { title: "Sign in" };

const ERRORS: Record<string, string> = {
  not_allowed: "That Google account isn't on the team list. Ask the owner to add your email on the Team page.",
  removed: "Your access was removed or changed. Sign in again, or ask the owner.",
  expired: "The sign-in took too long or was interrupted. Please try again.",
  cancelled: "Sign-in was cancelled.",
  google: "Google sign-in didn't work. Please try again in a minute.",
  setup: "Google sign-in isn't set up yet: GOOGLE_CLIENT_ID is missing from the dashboard's settings.",
};

export default function LoginPage(props: PageProps<"/login">) {
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-8 shadow-sm">
        <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-xl bg-accent-soft text-accent">
          <ChatIcon />
        </div>
        <h1 className="text-xl font-semibold">Lead dashboard</h1>
        <p className="mt-1 text-sm text-muted">
          WhatsApp enquiries and every conversation with the bot. Sign in with the Google account the owner added.
        </p>
        <Suspense fallback={<SignInButton next="/" />}>
          <SignIn searchParams={props.searchParams} />
        </Suspense>
      </div>
    </main>
  );
}

async function SignIn({ searchParams }: { searchParams: PageProps<"/login">["searchParams"] }) {
  const params = await searchParams;
  const error = typeof params.error === "string" ? ERRORS[params.error] : undefined;
  const next = safeNext(typeof params.next === "string" ? params.next : "/");
  return (
    <>
      {error && (
        <p role="alert" className="mt-5 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      <SignInButton next={next} />
    </>
  );
}

function SignInButton({ next }: { next: string }) {
  return (
    // a plain link, not <Link>: it leaves the app for Google
    <a
      href={`/auth/google${next === "/" ? "" : `?next=${encodeURIComponent(next)}`}`}
      className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm font-medium hover:bg-surface-2"
    >
      <GoogleIcon />
      Sign in with Google
    </a>
  );
}

function ChatIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-5.1A8 8 0 1 1 21 12Z" strokeLinejoin="round" />
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}
