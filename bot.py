"""Conversation logic: menu -> project pack -> FAQ, then the optional AI fallback, or hand-off to sales."""

import logging
import re
import time
from collections import OrderedDict

from ai import build_facts, sales_topics
from history import NoHistory
from maps import MapsResolver
from whatsapp import e164

log = logging.getLogger("bot.logic")

GREETINGS = {
    "hi", "hii", "hiii", "hello", "helo", "hey", "hlo", "hy", "menu", "start", "namaste",
    "namaskar", "projects", "project", "gm", "good", "info", "details", "interested", "enquiry",
}

DEFAULT_MESSAGES = {
    "welcome": "Hi {name}! Welcome to {company}.\n\nTap *View projects* to see our projects with flats available. "
    "You'll get the brochure, location and current availability.",
    "menu_button": "View projects",
    "menu_footer": "Type MENU anytime to see this list again",
    "site_details": "*{site_name}*\n\n{availability}\n\nWhat would you like to do next?",
    "btn_visit": "Book site visit",
    "btn_price": "Price details",
    "btn_sales": "Talk to sales",
    "visit_reply": "Thank you! Our team will call you shortly to fix a site visit at {site_name}. "
    "You can also reach {sales_name} directly:",
    "handoff": "Thanks for your message. Our sales team will call you shortly. "
    "You can also reach {sales_name} directly:",
    "faq_footer": "Type MENU to see all projects.",
    "non_text": "I can read text messages only.",
    "no_sites": "We don't have any flats listed right now. Our team will get back to you shortly.",
}


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def normalize(text):
    text = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _contains(text, phrase):
    return bool(phrase) and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def find_site_in_text(text, sites):
    """A project the customer named, by its name or any of its aliases."""
    for site in sites:
        names = [site["name"]] + site.get("aliases", [])
        if any(_contains(text, normalize(n)) for n in names):
            return site
    return None


def match_faq(text, faq, site_id=""):
    """Best FAQ row. A SALES row wins whenever it matches; otherwise most keyword hits,
    and a project-specific row beats a general one on a tie."""
    best, best_score = None, (0, 0, 0)
    for row in faq:
        if row["site_id"] and row["site_id"] != site_id:
            continue
        hits = sum(1 for kw in row["keywords"] if _contains(text, normalize(kw)))
        score = (1 if row["to_sales"] else 0, hits, 1 if row["site_id"] else 0)
        if hits and score > best_score:
            best, best_score = row, score
    return best


ALERT_COOLDOWN = 6 * 3600  # seconds before the same customer/project/event alerts sales again
AI_LIMIT_PER_HOUR = 10    # AI answers per customer per hour; beyond that a person takes over (keeps the bill small)


def split_phones(value):
    """'98765 43210, +91 91234 56789' -> ['+919876543210', '+919123456789'] (no duplicates)."""
    phones = []
    for part in re.split(r"[,;/\n]+", str(value or "")):
        number = e164(part)
        if number and number not in phones:
            phones.append(number)
    return phones


def is_greeting(text):
    words = text.split()
    return bool(words) and (text in GREETINGS or words[0] in GREETINGS)


class Bot:
    def __init__(self, wa, store, company, default_sales_name, default_sales_phone,
                 alert_template="", alert_language="en", maps=None,
                 default_alert_phones="", alert_on="handoffs", history=None, ai=None):
        self.wa = wa
        self.store = store
        self.history = history or NoHistory()  # conversation log for the dashboard (history.py)
        self.maps = maps or MapsResolver()
        self.ai = ai                    # optional AI fallback (ai.Gemini); None = keyword FAQ only
        self.ai_used = {}               # phone -> times of recent AI answers (AI_LIMIT_PER_HOUR)
        self.company = company
        self.default_sales = (default_sales_name, default_sales_phone)
        self.alert_template = alert_template
        self.alert_language = alert_language
        self.default_alert_phones = split_phones(default_alert_phones)
        self.alert_on_open = alert_on.strip().lower() == "all"  # also alert when a project is opened
        self.alerted = {}               # (customer, site, event) -> time, so repeat taps don't re-alert
        self.current_site = {}          # phone -> site_id (falls back to the Leads tab after a restart)
        self.seen = OrderedDict()       # message ids already handled; Meta retries webhooks

    # --- entry points ----------------------------------------------------

    def handle_webhook(self, payload):
        handled = 0
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                names = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
                for msg in value.get("messages", []):
                    if self.handle_message(msg, names.get(msg.get("from"), "")):
                        handled += 1
                for update in value.get("statuses", []):  # sent / delivered / read / failed
                    self.history.status(update)
        return handled

    def handle_message(self, msg, name):
        mid = msg.get("id", "")
        if mid in self.seen:
            return False
        self.seen[mid] = True
        while len(self.seen) > 5000:
            self.seen.popitem(last=False)

        phone = msg.get("from", "")
        self.history.incoming(phone, name, msg)
        try:
            self.wa.mark_read(mid)
        except Exception:
            log.exception("mark_read failed")

        ctx = _Ctx(self, phone, name)
        mtype = msg.get("type")
        if mtype == "interactive":
            reply = msg["interactive"].get("list_reply") or msg["interactive"].get("button_reply") or {}
            self.on_choice(ctx, reply.get("id", ""))
        elif mtype == "button":  # quick-reply button on a template message
            self.on_text(ctx, msg["button"].get("payload") or msg["button"].get("text", ""))
        elif mtype == "text":
            self.on_text(ctx, msg["text"].get("body", ""))
        else:
            self.wa.text(phone, ctx.fmt("non_text"))
            self.handoff(ctx, ctx.site, f"Sent a {mtype} message", event="non_text")
        return True

    # --- handlers --------------------------------------------------------

    def on_choice(self, ctx, choice_id):
        action, _, site_id = choice_id.partition(":")
        site = ctx.site_by_id(site_id)
        if action == "site" and site:
            self.send_site_pack(ctx, site)
        elif action == "visit" and site:
            ctx.set_site(site)
            self.handoff(ctx, site, "Wants a site visit", event="visit_request", message_key="visit_reply")
        elif action == "price" and site:
            ctx.set_site(site)
            answer = match_faq("price", ctx.faq, site["site_id"])
            if answer and not answer["to_sales"]:
                self.send_answer(ctx, answer, "Tapped Price details")
            else:  # no price row, or price is a SALES topic
                self.handoff(ctx, site, "Asked for price details", event="price_request")
        elif action == "sales":
            if site:
                ctx.set_site(site)
            self.handoff(ctx, ctx.site, "Tapped Talk to sales", event="sales_request")
        else:  # unknown id, or a project that was switched off since the menu was sent
            self.send_menu(ctx, "Tapped an old menu option")

    def on_text(self, ctx, raw):
        text = normalize(raw)
        named = find_site_in_text(text, ctx.sites)
        if named:
            ctx.set_site(named)
        answer = match_faq(text, ctx.faq, ctx.site["site_id"] if ctx.site else "")
        if answer and answer["to_sales"]:  # a topic the owner wants a person to handle
            self.handoff_question(ctx, raw)
        elif answer:
            self.send_answer(ctx, answer, raw)
        elif named:
            self.send_site_pack(ctx, named)
        elif is_greeting(text):
            self.send_menu(ctx, raw)
        elif not self.ai_answer(ctx, raw):  # keywords missed: the AI may answer from the Sheet, else a person
            self.handoff_question(ctx, raw)

    def ai_answer(self, ctx, raw):
        """The AI fallback (ai.py). True if it answered from the Sheet's own content; False means hand off."""
        if not self.ai:
            return False
        now = time.time()
        recent = [t for t in self.ai_used.get(ctx.phone, []) if now - t < 3600]
        if len(recent) >= AI_LIMIT_PER_HOUR:
            return False
        site = ctx.site
        # {name} is blanked so the customer's name never goes to the AI
        facts = build_facts(ctx.sites, ctx.faq, lambda text, s: ctx.fmt_text(text.replace("{name}", ""), s))
        topics = sales_topics(ctx.faq, site["site_id"] if site else "")
        try:
            reply = self.ai.answer(raw, facts, topics, site["name"] if site else "", self.company)
        except Exception:
            log.exception("AI fallback failed")
            return False
        if not reply:
            return False
        self.ai_used[ctx.phone] = recent + [now]
        footer = ctx.fmt("faq_footer")
        self.wa.text(ctx.phone, reply + (f"\n\n{footer}" if footer else ""))
        self.log(ctx, site, "ai_answered", raw)
        return True

    def handoff_question(self, ctx, raw):
        had_site = ctx.site is not None
        self.handoff(ctx, ctx.site, raw)
        if not had_site:  # a newcomer: show them the projects too
            self.send_menu(ctx, "", log_it=False)

    # --- replies ---------------------------------------------------------

    def send_menu(self, ctx, detail, log_it=True):
        if not ctx.sites:
            self.wa.text(ctx.phone, ctx.fmt("no_sites"))
            self.handoff(ctx, None, detail or "Asked for projects (none active)")
            return
        if len(ctx.sites) > 10:
            log.warning("%d active sites; WhatsApp lists show only the first 10", len(ctx.sites))
        rows = [(f"site:{s['site_id']}", s["name"], s["tagline"]) for s in ctx.sites]
        self.wa.list_menu(ctx.phone, self.company, ctx.fmt("welcome"), ctx.fmt("menu_footer"),
                          ctx.fmt("menu_button"), rows)
        if log_it:
            self.log(ctx, None, "menu_shown", detail)

    def send_site_pack(self, ctx, site):
        ctx.set_site(site)
        # latitude/longitude in the Sheet win; otherwise read them from the Google Maps link
        coords = None
        if site["latitude"] is not None and site["longitude"] is not None:
            coords = (site["latitude"], site["longitude"])
        elif site["maps_link"]:
            coords = self.maps.coords(site["maps_link"])
        if coords:
            self.wa.location(ctx.phone, coords[0], coords[1], site["name"], site["address"])
        elif site["address"] or site["maps_link"]:
            lines = [f"*{site['name']}* location:", site["address"], site["maps_link"]]
            self.wa.text(ctx.phone, "\n".join(line for line in lines if line))
        # brochure + availability + next-step buttons in ONE message, so they always arrive together
        self.wa.buttons(
            ctx.phone,
            ctx.fmt("site_details", site),
            [(f"visit:{site['site_id']}", ctx.fmt("btn_visit")),
             (f"price:{site['site_id']}", ctx.fmt("btn_price")),
             (f"sales:{site['site_id']}", ctx.fmt("btn_sales"))],
            header_text=site["name"],
            document_url=site["brochure_url"],
            document_filename=site["brochure_filename"],
        )
        self.log(ctx, site, "site_selected")
        if self.alert_on_open:
            self.alert(ctx, site, "site_selected", "Opened the project details")

    def send_answer(self, ctx, row, question):
        footer = ctx.fmt("faq_footer")
        self.wa.text(ctx.phone, ctx.fmt_text(row["answer"], ctx.site) + (f"\n\n{footer}" if footer else ""))
        self.log(ctx, ctx.site, "faq_answered", question)

    def handoff(self, ctx, site, detail, event="handoff", message_key="handoff"):
        sales_name, sales_phone = ctx.sales_for(site)
        self.wa.text(ctx.phone, ctx.fmt(message_key, site))
        if sales_phone:
            self.wa.contact(ctx.phone, sales_name, sales_phone)
        self.log(ctx, site, event, detail)
        self.alert(ctx, site, event, detail)

    def log(self, ctx, site, event, detail=""):
        """A lead event: a row in the Sheet's Leads tab, and in the dashboard."""
        self.store.log_lead(ctx.phone, ctx.name, site, event, detail)
        self.history.event(ctx.phone, ctx.name, site, event, detail)

    def alert_phones_for(self, site):
        """The project's alert_phones; else its salesperson; else the defaults from the settings."""
        if site:
            phones = split_phones(site.get("alert_phones", "")) or split_phones(site["sales_phone"])
            if phones:
                return phones
        return self.default_alert_phones or split_phones(self.default_sales[1])

    def alert(self, ctx, site, event, detail):
        """WhatsApp alert (an approved template) to everyone on the project's alert list."""
        if not self.alert_template:
            return
        key = (ctx.phone, site["site_id"] if site else "", event)
        now = time.time()
        if now - self.alerted.get(key, 0) < ALERT_COOLDOWN:
            return
        self.alerted[key] = now
        params = [ctx.name or "A customer", "+" + ctx.phone, site["name"] if site else "Not chosen yet", detail or event]
        phones = self.alert_phones_for(site)
        for phone in phones:
            try:
                self.wa.template(phone, self.alert_template, self.alert_language, params)
            except Exception:
                log.exception("Sales alert to %s failed", phone)
        # dashboard only (not the Leads tab): shows on the customer's conversation who was alerted
        self.history.event(ctx.phone, ctx.name, site, "sales_alerted", ", ".join(phones))


class _Ctx:
    """Everything one incoming message needs, read once from the sheet."""

    def __init__(self, bot, phone, name):
        self.bot, self.phone, self.name = bot, phone, name
        self.sites = bot.store.sites()
        self.faq = bot.store.faq()
        self.messages = {**DEFAULT_MESSAGES, **bot.store.messages()}
        self._site_loaded = False
        self._site = None

    def site_by_id(self, site_id):
        return next((s for s in self.sites if s["site_id"] == site_id), None)

    @property
    def site(self):
        if not self._site_loaded:
            site_id = self.bot.current_site.get(self.phone) or self.bot.store.last_site_id(self.phone)
            self._site = self.site_by_id(site_id) if site_id else None
            self._site_loaded = True
        return self._site

    def set_site(self, site):
        self._site, self._site_loaded = site, True
        self.bot.current_site[self.phone] = site["site_id"]

    def sales_for(self, site):
        if site and site["sales_phone"]:
            return site["sales_name"] or f"{self.bot.company} Sales", site["sales_phone"]
        return self.bot.default_sales

    def fmt_text(self, template, site=None):
        sales_name, sales_phone = self.sales_for(site)
        values = _SafeDict(
            name=self.name or "there",
            company=self.bot.company,
            site_name=site["name"] if site else "",
            availability=site["availability"] if site else "",
            sales_name=sales_name,
            sales_phone=e164(sales_phone),
        )
        try:
            return template.format_map(values).strip()
        except (ValueError, IndexError):  # a stray { or } typed in the sheet
            return template.strip()

    def fmt(self, key, site=None):
        return self.fmt_text(self.messages.get(key, ""), site)
