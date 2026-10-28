import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Fragment, Suspense } from "react";
import { Avatar } from "@/components/avatar";
import { FollowLatest, LiveRefresh } from "@/components/live";
import { MessageBubble } from "@/components/message";
import { Badge, primaryButton, secondaryButton, Skeleton } from "@/components/ui";
import { getCurrentUser } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { callLink, EVENT_LABELS, formatDay, formatPhone, formatTime, formatWhen, istDay, whatsappLink } from "@/lib/format";
import { getLead, getTimeline, type LeadEvent, type TimelineItem } from "@/lib/leads";

export const metadata: Metadata = { title: "Conversation" };

export default function LeadPage(props: PageProps<"/leads/[phone]">) {
  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <Link href="/" className="text-sm text-muted hover:text-text">
          ← All leads
        </Link>
        <LiveRefresh />
      </div>
      <Suspense fallback={<ConversationSkeleton />}>
        <Conversation params={props.params} />
      </Suspense>
    </>
  );
}

async function Conversation({ params }: { params: PageProps<"/leads/[phone]">["params"] }) {
  const { phone } = await params;
  const user = await getCurrentUser();
  if (!/^\d{6,15}$/.test(phone)) notFound();
  const db = await getDb();
  const lead = await getLead(db, user, phone);
  if (!lead) notFound(); // missing, or a rep opening another project's lead
  const timeline = await getTimeline(db, phone);
  const now = new Date();

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <div className="flex flex-wrap items-center gap-4 border-b border-line p-4">
        <Avatar name={lead.name} phone={lead.phone} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-semibold">{lead.name || formatPhone(lead.phone)}</h1>
          <p className="text-sm text-muted">
            {lead.name && `${formatPhone(lead.phone)} · `}first message {formatWhen(lead.first_seen, now)}
          </p>
          {lead.sites.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {lead.sites.map((s) => (
                <Badge key={s} tone="accent">
                  {s}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex basis-full gap-2 sm:basis-auto [&>a]:flex-1 sm:[&>a]:flex-none">
          <a href={callLink(lead.phone)} className={secondaryButton}>
            Call
          </a>
          <a href={whatsappLink(lead.phone)} target="_blank" rel="noreferrer" className={primaryButton}>
            WhatsApp
          </a>
        </div>
      </div>

      <div className="space-y-2 bg-chat px-3 py-4 sm:px-6">
        {timeline.length === 0 && <p className="py-8 text-center text-sm text-muted">No messages saved yet.</p>}
        {timeline.map((item, i) => (
          <Fragment key={`${item.type}-${item.id}`}>
            {(i === 0 || istDay(item.created_at) !== istDay(timeline[i - 1].created_at)) && (
              <DayDivider date={item.created_at} now={now} />
            )}
            {item.type === "message" ? <MessageBubble message={item} /> : <EventNote event={item} />}
          </Fragment>
        ))}
        <FollowLatest count={timeline.length} />
      </div>
      <p className="border-t border-line px-4 py-2 text-xs text-muted">
        Shows the bot&apos;s chat on the WhatsApp bot number. Calls and chats from the sales team&apos;s own phones
        aren&apos;t included.
      </p>
    </div>
  );
}

function DayDivider({ date, now }: { date: TimelineItem["created_at"]; now: Date }) {
  return (
    <div className="flex justify-center py-1">
      <span className="rounded-md bg-surface px-2.5 py-0.5 text-xs font-medium text-muted shadow-sm">
        {formatDay(date, now)}
      </span>
    </div>
  );
}

function EventNote({ event }: { event: LeadEvent }) {
  const meta = EVENT_LABELS[event.event];
  if (meta === null) return null;
  const label = meta?.label ?? event.event;
  const tones = {
    info: "bg-surface text-muted",
    action: "bg-action-soft text-action",
    alert: "bg-accent-soft text-accent",
  };
  const detail =
    event.event === "site_selected"
      ? event.site_name
      : event.event === "sales_alerted"
        ? event.detail && `sent to ${event.detail.split(/,\s*/).map(formatPhone).join(", ")}`
        : event.site_name;
  return (
    <div className="flex justify-center py-0.5">
      <span className={`max-w-[90%] rounded-full px-3 py-1 text-center text-xs font-medium ${tones[meta?.tone ?? "info"]}`}>
        {label}
        {detail ? ` · ${detail}` : ""} · {formatTime(event.created_at)}
      </span>
    </div>
  );
}

function ConversationSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <div className="flex items-center gap-4 border-b border-line p-4">
        <Skeleton className="h-12 w-12 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-3 w-64" />
        </div>
      </div>
      <div className="space-y-3 bg-chat p-6">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="ml-auto h-24 w-2/3" />
        <Skeleton className="h-10 w-1/3" />
      </div>
    </div>
  );
}
