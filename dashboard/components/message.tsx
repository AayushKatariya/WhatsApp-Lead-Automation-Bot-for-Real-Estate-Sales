import { formatPhone, formatTime, KIND_LABELS, mapsLink, whatsappParts } from "@/lib/format";
import type { Message } from "@/lib/leads";

// Payloads are stored exactly as Meta sent or received them, so read them defensively.
type Json = Record<string, unknown>;
const obj = (value: unknown): Json => (value && typeof value === "object" && !Array.isArray(value) ? (value as Json) : {});
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const str = (value: unknown): string => (typeof value === "string" ? value : "");
/** Only web links: the brochure URL comes from the Sheet, which many people can edit. */
const webUrl = (value: unknown): string | undefined => (/^https?:\/\//i.test(str(value)) ? str(value) : undefined);

export function WhatsAppText({ text }: { text: string }) {
  return (
    <p className="whitespace-pre-wrap break-words">
      {whatsappParts(text).map((part, i) =>
        part.style === "bold" ? (
          <strong key={i}>{part.text}</strong>
        ) : part.style === "italic" ? (
          <em key={i}>{part.text}</em>
        ) : part.style === "strike" ? (
          <s key={i}>{part.text}</s>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </p>
  );
}

export function MessageBubble({ message }: { message: Message }) {
  const out = message.direction === "out";
  return (
    <div className={`flex ${out ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-3 py-2 text-sm shadow-sm sm:max-w-[70%] ${
          out ? "rounded-tr-sm bg-bubble-out" : "rounded-tl-sm bg-bubble-in"
        }`}
      >
        {out ? <Outgoing message={message} /> : <Incoming message={message} />}
        <div className="mt-1 flex items-center justify-end gap-1 text-[11px] text-muted">
          {out && <span className="mr-auto font-medium">Bot</span>}
          <time dateTime={new Date(message.created_at).toISOString()}>{formatTime(message.created_at)}</time>
          {out && <Ticks status={message.status} />}
        </div>
        {message.error && (
          <p className="mt-1.5 rounded-md bg-danger-soft px-2 py-1 text-xs text-danger">
            Not delivered: {message.error}
          </p>
        )}
      </div>
    </div>
  );
}

function Ticks({ status }: { status: string }) {
  if (status === "failed") return <span className="text-danger" title="Failed">⚠</span>;
  const label = { sent: "Sent", delivered: "Delivered", read: "Read" }[status] ?? "Sending";
  return (
    <span className={status === "read" ? "text-read" : ""} title={label} aria-label={label}>
      {status === "delivered" || status === "read" ? "✓✓" : "✓"}
    </span>
  );
}

function KindLabel({ kind }: { kind: string }) {
  return (
    <span className="mb-1 inline-flex items-center gap-1 text-xs font-medium text-muted">
      {KIND_LABELS[kind] ?? kind}
    </span>
  );
}

function Incoming({ message }: { message: Message }) {
  const payload = obj(message.payload);
  const part = obj(payload[message.kind]);
  switch (message.kind) {
    case "text":
      return <WhatsAppText text={str(obj(payload.text).body) || message.body} />;
    case "interactive":
    case "button":
      return (
        <div>
          <KindLabel kind={message.kind} />
          <p className="font-medium">{message.body || "a button"}</p>
        </div>
      );
    case "location":
      return (
        <div>
          <KindLabel kind="location" />
          {message.body && <p>{message.body}</p>}
          <a
            href={mapsLink(part.latitude, part.longitude)}
            target="_blank"
            rel="noreferrer"
            className="text-accent underline"
          >
            Open in Google Maps
          </a>
        </div>
      );
    case "reaction":
      return <p className="text-2xl leading-none">{str(part.emoji) || "Reaction removed"}</p>;
    default:
      return (
        <div>
          <KindLabel kind={message.kind} />
          {message.body && <WhatsAppText text={message.body} />}
          <p className="text-xs text-muted">Voice notes, photos and files aren&apos;t shown here yet. Call them back.</p>
        </div>
      );
  }
}

function Outgoing({ message }: { message: Message }) {
  const payload = obj(message.payload);
  switch (message.kind) {
    case "text":
      return <WhatsAppText text={str(payload.body) || message.body} />;
    case "interactive":
      return <Interactive payload={payload} />;
    case "location":
      return (
        <div>
          <KindLabel kind="location" />
          <p className="font-medium">{str(payload.name)}</p>
          {str(payload.address) && <p className="text-muted">{str(payload.address)}</p>}
          <a
            href={mapsLink(payload.latitude, payload.longitude)}
            target="_blank"
            rel="noreferrer"
            className="text-accent underline"
          >
            Open in Google Maps
          </a>
        </div>
      );
    case "contacts": {
      const card = obj(list(message.payload)[0]);
      const phone = str(obj(list(card.phones)[0]).phone);
      return (
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-2 text-muted" aria-hidden="true">
            👤
          </span>
          <div>
            <p className="font-medium">{str(obj(card.name).formatted_name) || "Contact"}</p>
            <p className="text-muted">{formatPhone(phone)}</p>
          </div>
        </div>
      );
    }
    default:
      return message.body ? <WhatsAppText text={message.body} /> : <KindLabel kind={message.kind} />;
  }
}

/** A list menu, or reply buttons with a brochure (document) or text header. */
function Interactive({ payload }: { payload: Json }) {
  const header = obj(payload.header);
  const document = obj(header.document);
  const action = obj(payload.action);
  const rows = list(action.sections).flatMap((section) => list(obj(section).rows)).map(obj);
  const buttons = list(action.buttons).map((b) => obj(obj(b).reply));
  return (
    <div className="space-y-2">
      {header.type === "document" && (
        <a
          href={webUrl(document.link)}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 rounded-lg bg-surface/70 px-2.5 py-2 hover:bg-surface"
        >
          <span className="rounded bg-danger px-1.5 py-0.5 text-[10px] font-bold text-white">PDF</span>
          <span className="truncate font-medium">{str(document.filename) || "Brochure"}</span>
        </a>
      )}
      {header.type === "text" && <p className="font-semibold">{str(header.text)}</p>}
      <WhatsAppText text={str(obj(payload.body).text)} />
      {str(obj(payload.footer).text) && <p className="text-xs text-muted">{str(obj(payload.footer).text)}</p>}
      {rows.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-line bg-surface/70">
          <p className="border-b border-line px-2.5 py-1.5 text-center text-xs font-medium text-accent">
            ☰ {str(action.button) || "Menu"}
          </p>
          <ul className="divide-y divide-line">
            {rows.map((row, i) => (
              <li key={i} className="px-2.5 py-1.5">
                <p className="font-medium">{str(row.title)}</p>
                {str(row.description) && <p className="text-xs text-muted">{str(row.description)}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {buttons.length > 0 && (
        <div className="flex flex-col gap-1">
          {buttons.map((b, i) => (
            <span key={i} className="rounded-lg bg-surface/70 px-2.5 py-1.5 text-center text-xs font-medium text-accent">
              {str(b.title)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
