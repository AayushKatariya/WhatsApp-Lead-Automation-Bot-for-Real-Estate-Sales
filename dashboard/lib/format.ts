const IST = "Asia/Kolkata";

const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" });
const time = new Intl.DateTimeFormat("en-IN", { timeZone: IST, hour: "numeric", minute: "2-digit", hour12: true });
const dayMonth = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "numeric", month: "short" });
const fullDate = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "numeric", month: "short", year: "numeric" });
const weekdayDate = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST,
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** 2026-10-28, in India time: for grouping a conversation by day */
export function istDay(date: Date | string): string {
  return dayKey.format(new Date(date));
}

export function formatTime(date: Date | string): string {
  return time.format(new Date(date)).replace(/\s?(am|pm)$/i, (m) => m.toLowerCase());
}

/** Short and relative to now: "11:05 am" today, "26 Oct" this year, "26 Oct 2025" before that. */
export function formatWhen(date: Date | string, now: Date = new Date()): string {
  const d = new Date(date);
  if (istDay(d) === istDay(now)) return formatTime(d);
  if (istDay(d).slice(0, 4) === istDay(now).slice(0, 4)) return dayMonth.format(d);
  return fullDate.format(d);
}

export function formatDay(date: Date | string, now: Date = new Date()): string {
  const d = new Date(date);
  if (istDay(d) === istDay(now)) return "Today";
  if (istDay(d) === istDay(new Date(now.getTime() - 86_400_000))) return "Yesterday";
  return weekdayDate.format(d);
}

/** "919812345678" -> "+91 98123 45678" */
export function formatPhone(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("91")) return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`;
  return digits ? `+${digits}` : phone;
}

export const whatsappLink = (phone: string) => `https://wa.me/${phone.replace(/\D/g, "")}`;
export const callLink = (phone: string) => `tel:+${phone.replace(/\D/g, "")}`;
export const mapsLink = (lat: unknown, lng: unknown) => `https://www.google.com/maps?q=${Number(lat)},${Number(lng)}`;

/** What each lead event means, in plain words. null = not shown in the conversation. */
export const EVENT_LABELS: Record<string, { label: string; tone: "info" | "action" | "alert" } | null> = {
  menu_shown: null,
  faq_answered: null,
  non_text: null,
  site_selected: { label: "Opened", tone: "info" },
  ai_answered: { label: "Answered by AI", tone: "info" }, // shown so owners can review AI replies
  price_request: { label: "Asked for the price", tone: "action" },
  visit_request: { label: "Wants a site visit", tone: "action" },
  sales_request: { label: "Asked to talk to sales", tone: "action" },
  handoff: { label: "Handed to sales", tone: "action" },
  sales_alerted: { label: "Sales team alerted", tone: "alert" },
};

/** Badges in the leads list, most urgent first. */
export const LEAD_BADGES: { event: string; label: string }[] = [
  { event: "visit_request", label: "Site visit" },
  { event: "sales_request", label: "Talk to sales" },
  { event: "price_request", label: "Price" },
  { event: "handoff", label: "Question" },
];

/** Names for messages that aren't text. */
export const KIND_LABELS: Record<string, string> = {
  audio: "Voice note",
  image: "Photo",
  video: "Video",
  document: "Document",
  sticker: "Sticker",
  location: "Location",
  contacts: "Contact card",
  reaction: "Reaction",
  interactive: "Tapped",
  button: "Tapped",
  unsupported: "Unsupported message",
};

/** WhatsApp's *bold*, _italic_ and ~strike~, split into parts to render (never as raw HTML). */
export function whatsappParts(text: string): { text: string; style?: "bold" | "italic" | "strike" }[] {
  const parts: { text: string; style?: "bold" | "italic" | "strike" }[] = [];
  const pattern = /\*([^*\n]+)\*|_([^_\n]+)_|~([^~\n]+)~/g;
  let last = 0;
  for (const m of text.matchAll(pattern)) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index) });
    if (m[1] !== undefined) parts.push({ text: m[1], style: "bold" });
    else if (m[2] !== undefined) parts.push({ text: m[2], style: "italic" });
    else parts.push({ text: m[3], style: "strike" });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}
