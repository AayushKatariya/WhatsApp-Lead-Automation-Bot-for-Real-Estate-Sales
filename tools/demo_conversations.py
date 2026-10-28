"""Fills a database with sample conversations made by the real bot code, for trying the dashboard locally.

Nothing goes to WhatsApp or Google: the WhatsApp API and the Sheet are simulated.
    cd dashboard && npm run db:dev            (leave it running: a local Postgres on port 5432)
    DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres python tools/demo_conversations.py
Never point it at the live database: it adds made-up customers.
"""

import itertools
import os
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot import Bot  # noqa: E402
from history import History  # noqa: E402
from sheets import parse_faq, parse_sites  # noqa: E402
from whatsapp import WhatsApp  # noqa: E402

SITES = parse_sites([
    {"site_id": "GV", "name": "Green Valley Residency", "aliases": "green valley, gv", "active": "Yes",
     "tagline": "2 & 3 BHK · Possession Dec 2027",
     "brochure_url": "https://drive.google.com/file/d/DEMO_FILE_ID/view", "brochure_filename": "Green Valley brochure.pdf",
     "availability": "2 BHK (1,050 sq ft): 5 flats left\n3 BHK (1,420 sq ft): 7 flats left",
     "latitude": "19.8762", "longitude": "75.3433", "address": "Beed Bypass, Chhatrapati Sambhajinagar",
     "sales_name": "Rahul (Sales)", "sales_phone": "98765 43210", "alert_phones": "98765 43210, 98111 22233"},
    {"site_id": "SH", "name": "Sunrise Heights", "aliases": "sunrise", "active": "Yes", "tagline": "3 BHK premium · Ready to move",
     "brochure_url": "https://example.com/sunrise-heights.pdf", "brochure_filename": "Sunrise Heights brochure.pdf",
     "availability": "3 BHK (1,650 sq ft): 2 flats left", "latitude": "19.8601", "longitude": "75.3290",
     "address": "Garkheda, Chhatrapati Sambhajinagar", "sales_name": "Sneha (Sales)", "sales_phone": "91234 56789"},
])
FAQ = parse_faq([
    {"keywords": "price, prices, rate, rates, cost, area, carpet area, sq ft", "answer": "SALES", "site_id": ""},
    {"keywords": "rera, rera number", "answer": "{site_name} is RERA registered: P52100012345.", "site_id": "GV"},
    {"keywords": "rera, rera number", "answer": "{site_name} is RERA registered: P52100067890.", "site_id": "SH"},
    {"keywords": "loan, home loan, bank, emi", "answer": "Home loans are available from SBI, HDFC and ICICI. "
     "Our team helps with the paperwork.", "site_id": ""},
    {"keywords": "amenities, gym, clubhouse", "answer": "{site_name} has a gym, a swimming pool, a clubhouse "
     "and a children's play area.", "site_id": "GV"},
    {"keywords": "site visit timings, office hours", "answer": "Our site offices are open 10 am to 7 pm, all days "
     "including Sunday.", "site_id": ""},
])


class DemoStore:
    """The Sheet, in memory."""

    def __init__(self):
        self.leads = []

    def sites(self):
        return SITES

    def faq(self):
        return FAQ

    def messages(self):
        return {}

    def log_lead(self, phone, name, site, event, detail=""):
        self.leads.append((phone, site["site_id"] if site else ""))

    def last_site_id(self, phone):
        return next((s for p, s in reversed(self.leads) if p == phone and s), "")


class FixedMaps:
    def coords(self, link):
        return None


def main():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("Set DATABASE_URL to a local database (see the top of this file).")
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute((ROOT / "dashboard" / "db" / "schema.sql").read_text(encoding="utf-8"))

    run = uuid.uuid4().hex[:8]  # unique message ids, so the script can run again
    sent_ids = []
    counter = itertools.count(1)

    def fake_meta(request):
        if b'"status"' in request.content:  # a read receipt, not a message
            return httpx.Response(200, json={"success": True})
        message_id = f"wamid.demo.{run}.out{next(counter)}"
        sent_ids.append(message_id)
        return httpx.Response(200, json={"messages": [{"id": message_id}]})

    history = History(url)
    wa = WhatsApp("demo", "demo", http=httpx.Client(transport=httpx.MockTransport(fake_meta)), on_sent=history.outgoing)
    bot = Bot(wa, DemoStore(), "Shree Builders", "Shree Builders Sales", "+91 90000 00000",
              alert_template="new_lead_alert", maps=FixedMaps(), history=history)
    incoming = itertools.count(1)

    def say(phone, name, kind, part):
        msg = {"id": f"wamid.demo.{run}.in{next(incoming)}", "from": phone, "type": kind, kind: part}
        bot.handle_webhook({"entry": [{"changes": [{"value": {
            "contacts": [{"wa_id": phone, "profile": {"name": name}}], "messages": [msg]}}]}]})

    def text(phone, name, body):
        say(phone, name, "text", {"body": body})

    def tap(phone, name, choice_id, title, kind="button_reply"):
        say(phone, name, "interactive", {"type": kind, kind: {"id": choice_id, "title": title}})

    def statuses(failed_index=None):
        """Meta's delivery updates: everything read, one brochure failed (if asked)."""
        updates = []
        for i, message_id in enumerate(sent_ids):
            if i == failed_index:
                updates.append({"id": message_id, "status": "failed", "errors": [
                    {"code": 131053, "title": "Media upload error",
                     "error_data": {"details": "Downloading the document from the link failed"}}]})
            else:
                updates += [{"id": message_id, "status": "delivered"}, {"id": message_id, "status": "read"}]
        bot.handle_webhook({"entry": [{"changes": [{"value": {"statuses": updates}}]}]})
        sent_ids.clear()

    def shift(phone, hours):
        """Move a conversation back in time, so the demo spans several days."""
        with psycopg.connect(url, autocommit=True) as conn:
            for table in ("messages", "events"):
                conn.execute(f"UPDATE {table} SET created_at = created_at - make_interval(hours => %s) WHERE phone = %s",
                             (hours, phone))
            conn.execute("UPDATE contacts SET first_seen = first_seen - make_interval(hours => %s), "
                         "last_seen = last_seen - make_interval(hours => %s) WHERE phone = %s", (hours, hours, phone))

    # A newcomer sends a voice note, three days ago
    say("919765400003", "", "audio", {"id": "media1", "mime_type": "audio/ogg"})
    statuses()
    shift("919765400003", 72)

    # Amit types a project name and asks for the RERA number and loans; yesterday
    text("919822200002", "Amit Deshmukh", "Sunrise heights details please")
    text("919822200002", "Amit Deshmukh", "RERA number?")
    text("919822200002", "Amit Deshmukh", "Which banks give home loan?")
    statuses(failed_index=1)  # the brochure couldn't be fetched
    shift("919822200002", 20)

    # Priya opens Green Valley, asks the carpet area (a SALES topic), then books a visit; today
    text("919811100001", "Priya Kulkarni", "Hi")
    tap("919811100001", "Priya Kulkarni", "site:GV", "Green Valley Residency", kind="list_reply")
    text("919811100001", "Priya Kulkarni", "What is the carpet area of the *3 BHK*?")
    tap("919811100001", "Priya Kulkarni", "visit:GV", "Book site visit")
    statuses()

    history.pool.close()
    print("Added 3 demo conversations. Open the dashboard to see them.")


if __name__ == "__main__":
    main()
