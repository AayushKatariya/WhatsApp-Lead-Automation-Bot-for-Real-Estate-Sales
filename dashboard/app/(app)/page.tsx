import Form from "next/form";
import Link from "next/link";
import { Suspense } from "react";
import { Avatar } from "@/components/avatar";
import { LiveRefresh } from "@/components/live";
import { Badge, EmptyState, inputClass, secondaryButton, Skeleton } from "@/components/ui";
import { getCurrentUser } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { formatPhone, formatWhen, KIND_LABELS, LEAD_BADGES } from "@/lib/format";
import { listLeads, listProjects, type LeadFilters, type LeadSummary } from "@/lib/leads";
import type { Project } from "@/lib/types";

type SearchParams = PageProps<"/">["searchParams"];

export default function LeadsPage(props: PageProps<"/">) {
  return (
    <>
      <div className="mb-5 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Leads</h1>
          <p className="text-sm text-muted">Everyone who messaged the WhatsApp bot, latest first.</p>
        </div>
        <LiveRefresh />
      </div>
      <Suspense fallback={<LeadsSkeleton />}>
        <Leads searchParams={props.searchParams} />
      </Suspense>
    </>
  );
}

function readFilters(params: Awaited<SearchParams>): LeadFilters {
  const one = (key: string) => (typeof params[key] === "string" ? (params[key] as string) : "");
  return {
    q: one("q").slice(0, 100),
    site: one("site"),
    followUp: one("follow") === "1",
    page: Number(one("page")) || 1,
  };
}

function pageLink(filters: LeadFilters, page: number) {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.site) params.set("site", filters.site);
  if (filters.followUp) params.set("follow", "1");
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? `/?${query}` : "/";
}

async function Leads({ searchParams }: { searchParams: SearchParams }) {
  const user = await getCurrentUser();
  const filters = readFilters(await searchParams);
  const db = await getDb();
  const [{ leads, hasMore, page }, projects] = await Promise.all([
    listLeads(db, user, filters),
    listProjects(db, user),
  ]);
  const filtered = Boolean(filters.q || filters.site || filters.followUp);
  const now = new Date();

  return (
    <>
      <Filters filters={filters} projects={projects} />
      {leads.length === 0 ? (
        filtered ? (
          <EmptyState title="No leads match these filters">
            <Link href="/" className="font-medium text-accent hover:underline">
              Clear filters
            </Link>
          </EmptyState>
        ) : (
          <EmptyState title={user.role === "owner" ? "No leads yet" : "No leads for your projects yet"}>
            Leads appear here as soon as someone messages your WhatsApp number.
          </EmptyState>
        )
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {leads.map((lead) => (
            <LeadRow key={lead.phone} lead={lead} now={now} />
          ))}
        </ul>
      )}
      {(page > 1 || hasMore) && (
        <nav className="mt-4 flex items-center justify-between text-sm">
          {page > 1 ? (
            <Link href={pageLink(filters, page - 1)} className={secondaryButton}>
              ← Newer
            </Link>
          ) : (
            <span />
          )}
          <span className="text-muted">Page {page}</span>
          {hasMore ? (
            <Link href={pageLink(filters, page + 1)} className={secondaryButton}>
              Older →
            </Link>
          ) : (
            <span />
          )}
        </nav>
      )}
    </>
  );
}

function Filters({ filters, projects }: { filters: LeadFilters; projects: Project[] }) {
  return (
    <Form action="/" className="mb-4 flex flex-wrap items-center gap-2">
      <input
        type="search"
        name="q"
        defaultValue={filters.q}
        placeholder="Search name, number or message"
        aria-label="Search leads"
        className={`${inputClass} min-w-0 flex-1 basis-56`}
      />
      <select
        name="site"
        defaultValue={filters.site}
        aria-label="Project"
        className={`${inputClass} w-auto max-w-[14rem]`}
      >
        <option value="">All projects</option>
        {projects.map((p) => (
          <option key={p.site_id} value={p.site_id}>
            {p.site_name || p.site_id}
          </option>
        ))}
      </select>
      <label className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm">
        <input type="checkbox" name="follow" value="1" defaultChecked={filters.followUp} className="accent-accent" />
        Needs follow-up
      </label>
      <button className={secondaryButton}>Apply</button>
    </Form>
  );
}

function preview(lead: LeadSummary): string {
  if (!lead.last_kind) return "";
  const who = lead.last_direction === "out" ? "Bot: " : "";
  const body = (lead.last_body ?? "").replace(/\s+/g, " ");
  if (["text", "interactive", "button"].includes(lead.last_kind)) return who + body;
  const kind = KIND_LABELS[lead.last_kind] ?? lead.last_kind;
  return who + (body ? `${kind}: ${body}` : kind);
}

function LeadRow({ lead, now }: { lead: LeadSummary; now: Date }) {
  const badges = LEAD_BADGES.filter((b) => lead.events.includes(b.event));
  return (
    <li>
      <Link href={`/leads/${lead.phone}`} className="flex gap-3 px-4 py-3 hover:bg-surface-2">
        <Avatar name={lead.name} phone={lead.phone} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="truncate font-medium">{lead.name || formatPhone(lead.phone)}</span>
            {lead.name && <span className="hidden text-xs text-muted sm:inline">{formatPhone(lead.phone)}</span>}
            <span className="ml-auto shrink-0 text-xs text-muted">{formatWhen(lead.last_seen, now)}</span>
          </div>
          <p className="truncate text-sm text-muted">{preview(lead)}</p>
          {(lead.sites.length > 0 || badges.length > 0) && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {lead.sites.map((s) => (
                <Badge key={s} tone="accent">
                  {s}
                </Badge>
              ))}
              {badges.map((b) => (
                <Badge key={b.event} tone="action">
                  {b.label}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </Link>
    </li>
  );
}

function LeadsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-10 w-full" />
      <div className="divide-y divide-line rounded-xl border border-line bg-surface">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="flex gap-3 px-4 py-3">
            <Skeleton className="h-10 w-10 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
