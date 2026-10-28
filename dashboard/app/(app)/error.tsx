"use client";

import { useEffect } from "react";
import { LIVE_EVERY_MS } from "@/components/live";

export default function AppError({ retry }: { error: unknown; retry: () => void }) {
  // A failed background update also lands here (for example while the database wakes up),
  // so keep trying quietly while the tab is open. retry() fetches the page again.
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") retry();
    }, LIVE_EVERY_MS);
    return () => clearInterval(timer);
  }, [retry]);

  return (
    <div className="rounded-xl border border-line bg-surface px-6 py-12 text-center">
      <p className="font-medium">Couldn&apos;t load this page</p>
      <p className="mt-2 text-sm text-muted">
        The database may be waking up or unreachable. This page tries again every few seconds. If it keeps happening,
        check the dashboard&apos;s logs in Google Cloud Run.
      </p>
      <button
        onClick={() => retry()}
        className="mt-5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-text hover:opacity-90"
      >
        Try again
      </button>
    </div>
  );
}
