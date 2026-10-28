"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

/** How often an open page fetches new messages. */
export const LIVE_EVERY_MS = 10_000;
/** Stop after this long without mouse, keyboard or touch, so the free database can sleep. */
const IDLE_MS = 15 * 60_000;
/** Treat a page as "at the bottom" within this many pixels. */
const BOTTOM_SLACK_PX = 160;

/**
 * Keeps the page up to date: re-fetches its server data every 10 seconds while the tab is
 * visible and someone is using it, and right away when they come back to the tab.
 * router.refresh() keeps scroll position and anything typed into the filters.
 */
export function LiveRefresh() {
  const router = useRouter();
  const [updating, startTransition] = useTransition();
  const [paused, setPaused] = useState(false);
  const busy = useRef(false);
  const updateNow = useRef(() => {});

  useEffect(() => {
    busy.current = updating;
  }, [updating]);

  useEffect(() => {
    let lastActive = Date.now();
    let lastRefresh = Date.now();
    let idle = false;

    const refresh = () => {
      if (busy.current) return;
      lastRefresh = Date.now();
      startTransition(() => router.refresh());
    };
    const setIdle = (value: boolean) => {
      if (idle === value) return;
      idle = value;
      setPaused(value);
    };
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastActive > IDLE_MS) setIdle(true);
      else if (Date.now() - lastRefresh >= LIVE_EVERY_MS) refresh();
    };
    const onActivity = () => {
      lastActive = Date.now();
      if (idle) {
        setIdle(false);
        refresh();
      }
    };
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      lastActive = Date.now();
      setIdle(false);
      if (Date.now() - lastRefresh > 2_000) refresh();
    };
    updateNow.current = () => {
      lastActive = Date.now();
      setIdle(false);
      refresh();
    };

    const timer = setInterval(tick, 1_000);
    const activity = ["pointerdown", "pointermove", "keydown", "wheel", "scroll", "touchstart"] as const;
    for (const name of activity) window.addEventListener(name, onActivity, { passive: true });
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      for (const name of activity) window.removeEventListener(name, onActivity);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [router]);

  return (
    <button
      type="button"
      onClick={() => updateNow.current()}
      title={
        paused
          ? "Paused because nobody has used this page for 15 minutes. Click to update now."
          : "New messages appear by themselves every 10 seconds. Click to update now."
      }
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-muted hover:bg-surface-2 hover:text-text"
    >
      <span
        aria-hidden
        className={`h-2 w-2 rounded-full ${paused ? "bg-muted" : "bg-accent"} ${updating ? "animate-pulse" : ""}`}
      />
      {paused ? "Paused" : "Live"}
    </button>
  );
}

/**
 * On a conversation page: when new items arrive while the reader is already at the bottom,
 * scroll down so they see them. Someone reading older messages higher up isn't moved.
 */
export function FollowLatest({ count }: { count: number }) {
  const atBottom = useRef(true);
  const seen = useRef(count);

  useEffect(() => {
    const check = () => {
      const page = document.documentElement;
      atBottom.current = page.scrollHeight - (window.scrollY + window.innerHeight) < BOTTOM_SLACK_PX;
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => {
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, []);

  useEffect(() => {
    if (count > seen.current && atBottom.current) {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
    }
    seen.current = count;
  }, [count]);

  return null;
}
