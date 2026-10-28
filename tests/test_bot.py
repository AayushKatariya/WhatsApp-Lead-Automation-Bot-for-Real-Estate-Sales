"""Simulated conversations. Run with:  python -m pytest -q"""

import hashlib
import hmac
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import Bot, match_faq, normalize  # noqa: E402
from sheets import parse_faq, parse_messages, parse_sites  # noqa: E402
from whatsapp import WhatsApp, direct_download_url, e164  # noqa: E402

SITES = parse_sites([
    {"site_id": "GV", "name": "Green Valley Residency", "aliases": "green valley, gv", "active": "Yes",
     "tagline": "2 & 3 BHK · Possession Dec 2027",
     "brochure_url": "https://drive.google.com/file/d/1AbC-xyz_123/view?usp=sharing",
     "brochure_filename": "Green Valley brochure.pdf", "availability": "2BHK: 5 left\n3BHK: 7 left",
     "latitude": "19.8762", "longitude": "75.3433", "address": "Beed Bypass, Aurangabad",
     "sales_name": "Rahul (Sales)", "sales_phone": "98765 43210"},
    {"site_id": "SH", "name": "Sunrise Heights", "aliases": "", "active": "yes", "tagline": "3 BHK",
     "brochure_url": "", "brochure_filename": "", "availability": "3BHK: 2 left",
     "latitude": "", "longitude": "", "address": "Garkheda, Aurangabad", "sales_name": "", "sales_phone": ""},
    {"site_id": "OLD", "name": "Old Project", "aliases": "", "active": "No", "tagline": "", "brochure_url": "",
     "brochure_filename": "", "availability": "Sold out", "latitude": "", "longitude": "", "address": "",
     "sales_name": "", "sales_phone": ""},
])
FAQ = parse_faq([
    {"keywords": "rera, rera number", "answer": "{site_name} RERA no: P123", "site_id": "GV"},
    {"keywords": "rera", "answer": "All our projects are RERA registered.", "site_id": ""},
    {"keywords": "price, cost, rate", "answer": "{site_name} starts at Rs 45 lakh.", "site_id": "GV"},
    {"keywords": "loan, home loan, bank", "answer": "Loans from SBI and HDFC.", "site_id": ""},
])


class FakeWA:
    def __init__(self):
        self.sent = []

    def __getattr__(self, kind):
        return lambda *args, **kwargs: self.sent.append((kind, args, kwargs))

    def kinds(self):
        return [k for k, *_ in self.sent if k != "mark_read"]


class FakeStore:
    def __init__(self, sites=SITES, faq=FAQ, messages=None):
        self._sites, self._faq, self._messages = sites, faq, messages or {}
        self.leads = []

    def sites(self):
        return self._sites

    def faq(self):
        return self._faq

    def messages(self):
        return self._messages

    def log_lead(self, phone, name, site, event, detail=""):
        self.leads.append((phone, name, site["site_id"] if site else "", event, detail))

    def last_site_id(self, phone):
        for p, _, site_id, _, _ in reversed(self.leads):
            if p == phone and site_id:
                return site_id
        return ""


def make_bot(**kw):
    wa, store = FakeWA(), kw.pop("store", FakeStore())
    bot = Bot(wa, store, "Shree Builders", "Office", "+91 90000 00000", **kw)
    return bot, wa, store


_n = 0


def text(body, phone="919812345678"):
    global _n
    _n += 1
    return {"id": f"wamid.{_n}", "from": phone, "type": "text", "text": {"body": body}}


def tap(choice_id, kind="list_reply", phone="919812345678"):
    global _n
    _n += 1
    return {"id": f"wamid.{_n}", "from": phone, "type": "interactive",
            "interactive": {"type": kind, kind: {"id": choice_id, "title": "x"}}}


def test_hi_shows_active_projects_only():
    bot, wa, store = make_bot()
    bot.handle_message(text("Hi!"), "Priya")
    assert wa.kinds() == ["list_menu"]
    _, args, _ = wa.sent[-1]
    rows = args[5]
    assert [r[0] for r in rows] == ["site:GV", "site:SH"]
    assert "Priya" in args[2] and "Shree Builders" in args[2]
    assert store.leads[-1][3] == "menu_shown"


def test_picking_a_project_sends_location_then_brochure_with_buttons():
    bot, wa, store = make_bot()
    bot.handle_message(tap("site:GV"), "Priya")
    assert wa.kinds() == ["location", "buttons"]
    _, args, kwargs = wa.sent[-1]
    assert "5 left" in args[1] and "Green Valley Residency" in args[1]
    assert [b[0] for b in args[2]] == ["visit:GV", "price:GV", "sales:GV"]
    assert kwargs["document_url"].startswith("https://drive.google.com/")
    assert store.leads[-1][2:4] == ("GV", "site_selected")


def test_project_without_coordinates_or_brochure():
    bot, wa, _ = make_bot()
    bot.handle_message(tap("site:SH"), "")
    assert wa.kinds() == ["text", "buttons"]
    assert "Garkheda" in wa.sent[-2][1][1]
    assert wa.sent[-1][2]["document_url"] == ""


def test_faq_uses_the_project_they_picked():
    bot, wa, store = make_bot()
    bot.handle_message(tap("site:GV"), "")
    bot.handle_message(text("what is the RERA number?"), "")
    assert wa.sent[-1][0] == "text"
    assert "Green Valley Residency RERA no: P123" in wa.sent[-1][1][1]
    assert "Type MENU" in wa.sent[-1][1][1]
    assert store.leads[-1][3] == "faq_answered"


def test_general_faq_before_any_project():
    bot, wa, _ = make_bot()
    bot.handle_message(text("is it rera approved"), "")
    assert "All our projects are RERA registered." in wa.sent[-1][1][1]


def test_typing_a_project_name_sends_its_pack():
    bot, wa, _ = make_bot()
    bot.handle_message(text("Hi, I'm interested in Green Valley"), "")
    assert wa.kinds() == ["location", "buttons"]


def test_named_project_plus_question_answers_for_that_project():
    bot, wa, _ = make_bot()
    bot.handle_message(text("price of gv flats?"), "")
    assert wa.sent[-1][1][1].startswith("Green Valley Residency starts at Rs 45 lakh.")


def test_unknown_question_hands_off_with_contact_card_and_menu_for_newcomer():
    bot, wa, store = make_bot()
    bot.handle_message(text("can I pay in dollars from Dubai?"), "Ali")
    assert wa.kinds() == ["text", "contact", "list_menu"]
    assert wa.sent[2][1][1:] == ("Office", "+91 90000 00000")
    assert store.leads[-1][3] == "handoff"
    assert store.leads[-1][4] == "can I pay in dollars from Dubai?"


def test_unknown_question_after_project_uses_project_salesperson():
    bot, wa, _ = make_bot()
    bot.handle_message(tap("site:GV"), "")
    wa.sent.clear()
    bot.handle_message(text("Is Vastu followed?"), "")
    assert wa.kinds() == ["text", "contact"]
    assert wa.sent[-1][1][1:] == ("Rahul (Sales)", "98765 43210")
    assert "Rahul (Sales)" in wa.sent[-2][1][1]


def test_buttons_visit_price_sales():
    bot, wa, store = make_bot()
    bot.handle_message(tap("visit:GV", "button_reply"), "")
    assert store.leads[-1][3] == "visit_request"
    assert "site visit at Green Valley Residency" in [s for s in wa.sent if s[0] == "text"][-1][1][1]
    bot.handle_message(tap("price:GV", "button_reply"), "")
    assert "45 lakh" in wa.sent[-1][1][1]
    bot.handle_message(tap("price:SH", "button_reply"), "")
    assert store.leads[-1][3] == "price_request"
    bot.handle_message(tap("sales:SH", "button_reply"), "")
    assert store.leads[-1][2:4] == ("SH", "sales_request")


# --- topics the owner wants a person to handle ("SALES" as the FAQ answer) ---

SALES_FAQ = parse_faq([
    {"keywords": "price, rate, area, sq ft, square feet", "answer": "Sales", "site_id": ""},
    {"keywords": "possession", "answer": "{site_name}: possession Dec 2027.", "site_id": "GV"},
    {"keywords": "loan, home loan", "answer": "Loans from SBI and HDFC.", "site_id": ""},
])


def test_sales_faq_row_hands_off_and_wins_over_other_answers():
    assert [r["to_sales"] for r in SALES_FAQ] == [True, False, False]
    bot, wa, store = make_bot(store=FakeStore(faq=SALES_FAQ), alert_template="t")
    bot.handle_message(tap("site:GV"), "Priya")
    wa.sent.clear()
    bot.handle_message(text("Carpet area in sq. ft.? And possession?"), "Priya")
    assert wa.kinds() == ["text", "contact", "template"]
    assert wa.sent[1][1][1].startswith("Thanks for your message.")  # the hand-off, never the word "Sales"
    assert wa.sent[2][1][1:] == ("Rahul (Sales)", "98765 43210")
    assert store.leads[-1][2:] == ("GV", "handoff", "Carpet area in sq. ft.? And possession?")
    assert wa.sent[3][1][3][3] == "Carpet area in sq. ft.? And possession?"  # what the alert tells sales


def test_sales_topic_from_a_newcomer_or_with_a_project_name():
    bot, wa, store = make_bot(store=FakeStore(faq=SALES_FAQ))
    bot.handle_message(text("rate for 2bhk?"), "Ali")
    assert wa.kinds() == ["text", "contact", "list_menu"]  # no project yet: the menu follows
    assert wa.sent[2][1][1:] == ("Office", "+91 90000 00000")
    wa.sent.clear()
    bot.handle_message(text("Green Valley price?"), "Ali")
    assert wa.kinds() == ["text", "contact"]  # a salesperson, not the brochure
    assert wa.sent[-1][1][1:] == ("Rahul (Sales)", "98765 43210")
    assert store.leads[-1][2:] == ("GV", "handoff", "Green Valley price?")


def test_price_button_hands_off_when_price_is_a_sales_topic():
    bot, wa, store = make_bot(store=FakeStore(faq=SALES_FAQ))
    bot.handle_message(tap("price:GV", "button_reply"), "")
    assert wa.kinds() == ["text", "contact"]
    assert store.leads[-1][2:4] == ("GV", "price_request")
    bot.handle_message(text("possession date?"), "")
    assert wa.sent[-1][1][1].startswith("Green Valley Residency: possession Dec 2027.")
    bot.handle_message(text("home loan available?"), "")
    assert wa.sent[-1][1][1].startswith("Loans from SBI and HDFC.")  # other rows still answer


def test_switched_off_project_in_old_menu_resends_menu():
    bot, wa, _ = make_bot()
    bot.handle_message(tap("site:OLD"), "")
    assert wa.kinds() == ["list_menu"]


def test_voice_note_gets_handoff():
    bot, wa, store = make_bot()
    bot.handle_message({"id": "wamid.voice", "from": "91981", "type": "audio", "audio": {}}, "")
    assert wa.kinds()[:2] == ["text", "text"]
    assert store.leads[-1][3] == "non_text"


def test_duplicate_webhook_is_ignored():
    bot, wa, _ = make_bot()
    msg = text("hi")
    assert bot.handle_message(msg, "")
    assert not bot.handle_message(msg, "")
    assert wa.kinds() == ["list_menu"]


def test_project_remembered_after_restart_via_leads_tab():
    store = FakeStore()
    bot, _, _ = make_bot(store=store)
    bot.handle_message(tap("site:GV"), "")
    bot2, wa2, _ = make_bot(store=store)  # fresh process, same sheet
    bot2.handle_message(text("rera"), "")
    assert "P123" in wa2.sent[-1][1][1]


def test_sales_alert_template():
    bot, wa, _ = make_bot(alert_template="new_lead_alert")
    bot.handle_message(tap("site:GV"), "Priya")
    bot.handle_message(text("Do you allow pets?"), "Priya")
    kind, args, _ = wa.sent[-1]
    assert kind == "template"
    assert args[0] == "+919876543210" and args[1] == "new_lead_alert"
    assert args[3] == ["Priya", "+919812345678", "Green Valley Residency", "Do you allow pets?"]


def test_messages_tab_overrides_and_bad_braces_dont_crash():
    store = FakeStore(messages=parse_messages([{"key": "welcome", "text": "Namaste {name}! {oops"}]))
    bot, wa, _ = make_bot(store=store)
    bot.handle_message(text("hello"), "Asha")
    assert wa.sent[-1][1][2] == "Namaste {name}! {oops"


def test_no_active_sites():
    bot, wa, _ = make_bot(store=FakeStore(sites=[]))
    bot.handle_message(text("hi"), "")
    assert wa.kinds() == ["text", "text", "contact"]


def test_webhook_payload_and_status_updates():
    bot, wa, _ = make_bot()
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "contacts": [{"wa_id": "919812345678", "profile": {"name": "Priya"}}],
        "messages": [text("hi")]}}, {"field": "messages", "value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert bot.handle_webhook(payload) == 1
    assert "Priya" in wa.sent[-1][1][2]


def test_helpers():
    assert e164("98765 43210") == "+919876543210"
    assert e164("+91-98765-43210") == "+919876543210"
    assert direct_download_url("https://drive.google.com/file/d/1AbC-xyz_123/view?usp=sharing") == \
        "https://drive.usercontent.google.com/download?id=1AbC-xyz_123&export=download"
    assert direct_download_url("https://example.com/a.pdf") == "https://example.com/a.pdf"
    assert normalize("RERA No.?") == "rera no"
    assert match_faq("home loan", FAQ)["answer"].startswith("Loans")


# --- payloads actually sent to Meta ------------------------------------

def capture_wa():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    no_downloads = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    return WhatsApp("TOKEN", "12345", http=client, downloader=no_downloads), calls


def test_payload_shapes_respect_whatsapp_limits():
    wa, calls = capture_wa()
    rows = [(f"site:{i}", f"Project with a very long name {i}", "x" * 100) for i in range(12)]
    wa.list_menu("91981", "Shree Builders", "Welcome", "footer", "View all our projects now", rows)
    menu = calls[-1]["interactive"]
    assert len(menu["action"]["sections"][0]["rows"]) == 10
    assert all(len(r["title"]) <= 24 and len(r["description"]) <= 72 for r in menu["action"]["sections"][0]["rows"])
    assert len(menu["action"]["button"]) <= 20

    wa.buttons("91981", "body", [("a", "Book site visit"), ("b", "Price details"), ("c", "Talk to sales")],
               header_text="GV", document_url="https://drive.google.com/file/d/ID9/view", document_filename="GV.pdf")
    b = calls[-1]
    assert b["messaging_product"] == "whatsapp" and b["type"] == "interactive"
    assert b["interactive"]["header"] == {"type": "document", "document": {
        "link": "https://drive.usercontent.google.com/download?id=ID9&export=download", "filename": "GV.pdf"}}

    wa.buttons("91981", "body", [("a", "A")], header_text="Sunrise Heights")
    assert calls[-1]["interactive"]["header"] == {"type": "text", "text": "Sunrise Heights"}

    wa.contact("91981", "Rahul", "98765 43210")
    assert calls[-1]["contacts"][0]["phones"][0] == {"phone": "+919876543210", "type": "WORK", "wa_id": "919876543210"}

    wa.template("+9198", "new_lead_alert", "en", ["Priya", "x\n\ny", ""])
    params = calls[-1]["template"]["components"][0]["parameters"]
    assert [p["text"] for p in params] == ["Priya", "x y", "-"]


def brochure_setup(download, upload_status=200):
    """A WhatsApp client whose brochure host returns `download` (status, content type, bytes)."""
    seen = {"downloads": [], "uploads": [], "messages": []}

    def meta(request):
        if request.url.path.endswith("/media"):
            seen["uploads"].append(request)
            if upload_status != 200:
                return httpx.Response(upload_status, json={"error": {"message": "bad"}})
            return httpx.Response(200, json={"id": "MEDIA1"})
        seen["messages"].append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})

    def host(request):
        seen["downloads"].append(request)
        status, content_type, body = download
        return httpx.Response(status, headers={"content-type": content_type}, content=body)

    wa = WhatsApp("TOKEN", "12345", http=httpx.Client(transport=httpx.MockTransport(meta), headers={"Authorization": "Bearer TOKEN"}),
                  downloader=httpx.Client(transport=httpx.MockTransport(host)))
    return wa, seen


def test_brochure_is_uploaded_once_and_arrives_as_a_pdf():
    # Google Drive answers application/octet-stream, which phones showed as a .bin file
    wa, seen = brochure_setup((200, "application/octet-stream", b"%PDF-1.7 brochure bytes"))
    for _ in range(2):
        wa.buttons("91981", "body", [("a", "A")], document_url="https://drive.google.com/file/d/ID9/view",
                   document_filename="Green Valley brochure")
    assert [m["interactive"]["header"]["document"] for m in seen["messages"]] == \
        [{"id": "MEDIA1", "filename": "Green Valley brochure.pdf"}] * 2
    assert len(seen["downloads"]) == 1 and len(seen["uploads"]) == 1  # the second send reuses the media id
    assert str(seen["downloads"][0].url) == "https://drive.usercontent.google.com/download?id=ID9&export=download"
    assert "authorization" not in seen["downloads"][0].headers  # the WhatsApp token never goes to Google Drive
    upload = seen["uploads"][0]
    assert str(upload.url) == "https://graph.facebook.com/v26.0/12345/media"
    form = upload.read()
    assert b'name="type"\r\n\r\napplication/pdf' in form and b"Content-Type: application/pdf" in form
    assert b'filename="Green Valley brochure.pdf"' in form


def test_brochure_falls_back_to_the_link_when_it_cannot_be_uploaded():
    link = {"link": "https://drive.usercontent.google.com/download?id=ID9&export=download", "filename": "GV.pdf"}
    for download, upload_status in (
        ((200, "text/html", b"<html>Google Drive can't scan this file</html>"), 200),  # not shared, or too big
        ((404, "text/html", b"not found"), 200),
        ((200, "application/pdf", b"%PDF-1.4"), 500),  # Meta refused the upload
    ):
        wa, seen = brochure_setup(download, upload_status)
        wa.buttons("91981", "body", [("a", "A")], document_url="https://drive.google.com/file/d/ID9/view",
                   document_filename="GV.pdf")
        assert seen["messages"][-1]["interactive"]["header"]["document"] == link


# --- the web server -----------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WA_VERIFY_TOKEN", "my-verify-token")
    monkeypatch.setenv("WA_APP_SECRET", "s3cret")
    sys.modules.pop("main", None)
    import main
    from fastapi.testclient import TestClient

    bot, wa, _ = make_bot()
    main._bot = bot
    return TestClient(main.app), wa


def test_webhook_verification(client):
    c, _ = client
    ok = c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "my-verify-token", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"}).status_code == 403


def test_signed_webhook_is_processed_unsigned_is_rejected(client):
    c, wa = client
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [text("hi")]}}]}]}).encode()
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert c.post("/webhook", content=body, headers={"X-Hub-Signature-256": sig}).status_code == 200
    assert wa.kinds() == ["list_menu"]
    assert c.post("/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 403


def test_sheet_store_against_a_fake_spreadsheet(monkeypatch):
    import google.auth
    import gspread
    from sheets import SheetStore

    class FakeWS:
        def __init__(self, records=None, values=None):
            self.records, self.values = records or [], values or [["timestamp", "phone", "name", "site_id"]]

        def get_all_records(self, numericise_ignore=()):
            assert numericise_ignore == ["all"]
            return self.records

        def append_row(self, row, value_input_option=None):
            assert value_input_option == "RAW"
            self.values.append(row)

        def get_all_values(self):
            return self.values

    tabs = {"Sites": FakeWS([{"site_id": "GV", "name": "Green Valley", "active": "Yes", "latitude": "19.8"}]),
            "FAQ": FakeWS([{"keywords": "rera", "answer": "Yes", "site_id": ""}]),
            "Leads": FakeWS()}

    class FakeBook:
        def worksheet(self, name):
            if name not in tabs:
                raise gspread.WorksheetNotFound(name)
            return tabs[name]

    class FakeClient:
        def open_by_key(self, key):
            assert key == "SHEET123"
            return FakeBook()

    monkeypatch.setattr(google.auth, "default", lambda scopes: (object(), "proj"))
    monkeypatch.setattr(gspread, "authorize", lambda creds: FakeClient())
    store = SheetStore("SHEET123")
    assert store.sites()[0]["latitude"] == 19.8
    assert store.faq()[0]["keywords"] == ["rera"]
    assert store.messages() == {}  # no Messages tab: defaults are used
    store.log_lead("9198", "Priya", store.sites()[0], "site_selected")
    store.log_lead("9198", "Priya", None, "faq_answered", "=HYPERLINK(\"x\")")
    assert tabs["Leads"].values[1][1:6] == ["9198", "Priya", "GV", "Green Valley", "site_selected"]
    assert store.last_site_id("9198") == "GV"


# --- Google Maps links instead of latitude/longitude ----------------------

from maps import MapsResolver, coords_from_text  # noqa: E402


def test_coordinates_read_from_common_maps_link_formats():
    assert coords_from_text("https://www.google.com/maps/place/Green+Valley/@19.8700,75.3400,17z/"
                            "data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d19.8762!4d75.3433") == (19.8762, 75.3433)
    assert coords_from_text("https://www.google.com/maps/@19.8762,75.3433,15z") == (19.8762, 75.3433)
    assert coords_from_text("https://maps.google.com/?q=19.8762,75.3433") == (19.8762, 75.3433)
    assert coords_from_text("https://www.google.com/maps/search/?api=1&query=19.8762%2C75.3433") == (19.8762, 75.3433)
    assert coords_from_text("https://www.google.com/maps/search/19.8762,+75.3433") == (19.8762, 75.3433)
    assert coords_from_text("https://maps.app.goo.gl/AbCdEf12345") is None


def resolver(routes):
    fetched = []

    def handler(request):
        fetched.append(str(request.url))
        status, headers, body = routes[str(request.url)]
        return httpx.Response(status, headers=headers, text=body)

    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return MapsResolver(http=http), fetched


def test_short_share_link_is_opened_to_find_the_pin():
    final = "https://www.google.com/maps/place/Green+Valley/@19.87,75.34,17z/data=!4m6!3m5!8m2!3d19.8762!4d75.3433"
    maps, fetched = resolver({
        "https://maps.app.goo.gl/AbC123": (302, {"location": final}, ""),
        final: (200, {}, "<html></html>"),
    })
    assert maps.coords("https://maps.app.goo.gl/AbC123") == (19.8762, 75.3433)
    assert maps.coords("https://maps.app.goo.gl/AbC123") == (19.8762, 75.3433)
    assert len(fetched) == 2  # second call answered from cache


def test_coordinates_found_in_page_when_url_has_none():
    page = '<meta content="https://maps.google.com/maps/api/staticmap?center=19.8762%2C75.3433&amp;zoom=15">'
    maps, _ = resolver({"https://maps.app.goo.gl/Xyz": (200, {}, page)})
    assert maps.coords("https://maps.app.goo.gl/Xyz") == (19.8762, 75.3433)


def test_unreadable_link_is_not_retried_immediately_and_other_sites_are_never_fetched():
    maps, fetched = resolver({"https://maps.app.goo.gl/Bad": (404, {}, "not found")})
    assert maps.coords("https://maps.app.goo.gl/Bad") is None
    assert maps.coords("https://maps.app.goo.gl/Bad") is None
    assert len(fetched) == 1
    assert maps.coords("https://example.com/my-site-map") is None
    assert len(fetched) == 1


class FakeMaps:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def coords(self, link):
        self.asked.append(link)
        return self.answer


def site_with_link(**overrides):
    row = {"site_id": "ML", "name": "Maple Towers", "active": "Yes", "availability": "2BHK: 3 left",
           "maps_link": "https://maps.app.goo.gl/Maple1", "address": "Example Road"}
    row.update(overrides)
    return parse_sites([row])


def test_maps_link_becomes_a_location_pin():
    maps = FakeMaps((18.5, 73.8))
    bot, wa, _ = make_bot(store=FakeStore(sites=site_with_link()), maps=maps)
    bot.handle_message(tap("site:ML"), "")
    assert wa.kinds() == ["location", "buttons"]
    assert wa.sent[1][1][1:4] == (18.5, 73.8, "Maple Towers")


def test_latitude_longitude_in_sheet_win_over_the_link():
    maps = FakeMaps((18.5, 73.8))
    bot, wa, _ = make_bot(store=FakeStore(sites=site_with_link(latitude="19.1", longitude="72.9")), maps=maps)
    bot.handle_message(tap("site:ML"), "")
    assert wa.sent[1][1][1:3] == (19.1, 72.9)
    assert maps.asked == []


def test_unreadable_link_is_sent_as_a_tappable_link():
    bot, wa, _ = make_bot(store=FakeStore(sites=site_with_link()), maps=FakeMaps(None))
    bot.handle_message(tap("site:ML"), "")
    assert wa.kinds() == ["text", "buttons"]
    assert wa.sent[1][1][1] == "*Maple Towers* location:\nExample Road\nhttps://maps.app.goo.gl/Maple1"


# --- alerts to several salespeople ---------------------------------------

from bot import split_phones  # noqa: E402


def alerts(wa):
    return [(args[0], args[3]) for kind, args, _ in wa.sent if kind == "template"]


def team_site(**overrides):
    row = {"site_id": "GV", "name": "Green Valley Residency", "active": "Yes", "availability": "2BHK: 5 left",
           "sales_name": "Rahul", "sales_phone": "98765 43210",
           "alert_phones": "98765 43210, +91 91234 56789; 9000011111\n+91 98765 43210"}
    row.update(overrides)
    return parse_sites([row])


def test_split_phones_handles_separators_and_duplicates():
    assert split_phones("98765 43210, +91 91234 56789; 9000011111\n+91 98765 43210") == \
        ["+919876543210", "+919123456789", "+919000011111"]
    assert split_phones("") == []


def test_every_number_in_alert_phones_gets_the_enquiry():
    bot, wa, _ = make_bot(store=FakeStore(sites=team_site()), alert_template="new_lead_alert")
    bot.handle_message(tap("visit:GV", "button_reply"), "Priya")
    sent = alerts(wa)
    assert [p for p, _ in sent] == ["+919876543210", "+919123456789", "+919000011111"]
    assert sent[0][1] == ["Priya", "+919812345678", "Green Valley Residency", "Wants a site visit"]
    # the customer still gets one contact card: the project's salesperson
    assert [args[1:] for kind, args, _ in wa.sent if kind == "contact"] == [("Rahul", "98765 43210")]


def test_blank_alert_phones_falls_back_to_salesperson_then_defaults():
    bot, wa, _ = make_bot(store=FakeStore(sites=team_site(alert_phones="")), alert_template="t")
    bot.handle_message(tap("sales:GV", "button_reply"), "")
    assert [p for p, _ in alerts(wa)] == ["+919876543210"]

    bot, wa, _ = make_bot(store=FakeStore(sites=team_site()), alert_template="t",
                          default_alert_phones="+91 90000 00001, +91 90000 00002")
    bot.handle_message(text("can I pay in dollars?"), "")  # no project picked yet
    assert [p for p, _ in alerts(wa)] == ["+919000000001", "+919000000002"]


def test_alert_on_all_also_alerts_when_a_project_is_opened():
    bot, wa, _ = make_bot(store=FakeStore(sites=team_site()), alert_template="t")
    bot.handle_message(tap("site:GV"), "")
    assert alerts(wa) == []  # default: hand-offs only

    bot, wa, _ = make_bot(store=FakeStore(sites=team_site()), alert_template="t", alert_on="all")
    bot.handle_message(tap("site:GV"), "Priya")
    assert len(alerts(wa)) == 3
    assert alerts(wa)[0][1][3] == "Opened the project details"


def test_repeat_taps_do_not_spam_the_team():
    bot, wa, _ = make_bot(store=FakeStore(sites=team_site()), alert_template="t")
    bot.handle_message(tap("visit:GV", "button_reply"), "")
    bot.handle_message(tap("visit:GV", "button_reply"), "")
    assert len(alerts(wa)) == 3          # second tap within 6 hours: no new alerts
    bot.handle_message(tap("sales:GV", "button_reply"), "")
    assert len(alerts(wa)) == 6          # a different request does alert


def test_no_template_configured_means_no_alerts():
    bot, wa, _ = make_bot(store=FakeStore(sites=team_site()))
    bot.handle_message(tap("visit:GV", "button_reply"), "")
    assert alerts(wa) == []


# --- conversation log for the dashboard (history.py) ----------------------

from contextlib import contextmanager  # noqa: E402

from history import History, describe_incoming, describe_outgoing  # noqa: E402


class FakeHistory:
    def __init__(self):
        self.calls = []

    def __getattr__(self, kind):
        return lambda *args: self.calls.append((kind, args))


def test_conversation_and_events_are_recorded_for_the_dashboard():
    history = FakeHistory()
    bot, _, store = make_bot(store=FakeStore(sites=team_site()), alert_template="t", history=history)
    bot.handle_message(tap("visit:GV", "button_reply"), "Priya")
    assert [kind for kind, _ in history.calls] == ["incoming", "event", "event"]
    assert history.calls[0][1][:2] == ("919812345678", "Priya")
    assert history.calls[1][1][3:] == ("visit_request", "Wants a site visit")
    assert history.calls[2][1][3:] == ("sales_alerted", "+919876543210, +919123456789, +919000011111")
    assert store.leads[-1][3] == "visit_request"  # the Sheet's Leads tab still gets its row


def test_delivery_updates_are_passed_on():
    history = FakeHistory()
    bot, _, _ = make_bot(history=history)
    update = {"id": "wamid.out1", "status": "failed", "errors": [{"code": 131053, "title": "Media upload error"}]}
    bot.handle_webhook({"entry": [{"changes": [{"value": {"statuses": [update]}}]}]})
    assert history.calls == [("status", (update,))]


def test_sent_messages_report_their_id_or_error():
    sent = []

    def handler(request):
        if json.loads(request.content).get("to") == "bad":
            return httpx.Response(400, json={"error": {"message": "Invalid parameter"}})
        return httpx.Response(200, json={"messages": [{"id": "wamid.out1"}]})

    wa = WhatsApp("TOKEN", "12345", http=httpx.Client(transport=httpx.MockTransport(handler)),
                  on_sent=lambda *args: sent.append(args))
    wa.text("919812345678", "Hello")
    wa.mark_read("wamid.in1")  # a read receipt, not a message: not reported
    wa.text("bad", "Hello")
    assert sent[0] == ("919812345678", "text", {"body": "Hello", "preview_url": True}, "wamid.out1", "")
    assert len(sent) == 2 and sent[1][3] == "" and sent[1][4].startswith("WhatsApp API error 400")


class FakePool:
    """Stands in for psycopg_pool.ConnectionPool: records SQL instead of running it."""

    def __init__(self, down=False):
        self.statements, self.down = [], down

    @contextmanager
    def connection(self):
        if self.down:
            raise ConnectionError("database unreachable")
        yield self

    def execute(self, sql, params):
        self.statements.append((" ".join(sql.split()), params))


def test_history_writes_messages_events_and_statuses():
    pool = FakePool()
    h = History(pool=pool)
    h.incoming("919812345678", "Priya", text("Price?"))
    assert pool.statements[0][0].startswith("INSERT INTO contacts") and "last_seen = now()" in pool.statements[0][0]
    sql, params = pool.statements[1]
    assert sql.startswith("INSERT INTO messages") and params[:3] == ("919812345678", "text", "Price?")
    assert json.loads(params[3])["text"]["body"] == "Price?" and params[4].startswith("wamid.")

    card = [{"name": {"formatted_name": "Rahul"}, "phones": [{"phone": "+919876543210"}]}]
    h.outgoing("919812345678", "contacts", card, "wamid.out1")
    assert pool.statements[2][1][:3] == ("919812345678", "contacts", "Rahul +919876543210")
    assert pool.statements[2][1][4:] == ("wamid.out1", "sent", "")
    h.outgoing("+919876543210", "template", {"name": "new_lead_alert"}, "wamid.out2")  # alert to sales: an event instead
    assert len(pool.statements) == 3

    h.status({"id": "wamid.out1", "status": "read"})
    h.status({"id": "wamid.out1", "status": "failed",
              "errors": [{"code": 131053, "title": "Media upload error", "error_data": {"details": "Bad PDF"}}]})
    h.status({"id": "wamid.out1", "status": "deleted"})  # not a delivery status: ignored
    assert pool.statements[3][1] == ("read", "", "", "wamid.out1", 3)
    assert pool.statements[4][1][1] == "131053 Media upload error Bad PDF"
    assert len(pool.statements) == 5

    h.event("919812345678", "Priya", SITES[0], "visit_request", "Wants a site visit")
    assert pool.statements[-1][1] == ("919812345678", "GV", "Green Valley Residency", "visit_request", "Wants a site visit")


def test_database_trouble_never_stops_the_bot():
    history = History(pool=FakePool(down=True))
    bot, wa, store = make_bot(history=history)
    bot.handle_message(text("hi"), "")
    history.outgoing("919812345678", "text", {"body": "x"})
    history.status({"id": "wamid.x", "status": "read"})
    assert wa.kinds() == ["list_menu"] and store.leads[-1][3] == "menu_shown"


def test_readable_text_for_each_message_type():
    assert describe_incoming(tap("site:GV")) == "x"  # the title of the tapped row
    assert describe_incoming({"type": "audio", "audio": {"id": "m1"}}) == ""
    assert describe_incoming({"type": "image", "image": {"caption": "Is this the view?"}}) == "Is this the view?"
    assert describe_incoming({"type": "location", "location": {"latitude": 19.8, "longitude": 75.3}}) == "19.8, 75.3"
    assert describe_outgoing("interactive", {"type": "button", "body": {"text": "Pick one"}}) == "Pick one"
    assert describe_outgoing("location", {"name": "Green Valley", "address": "Beed Bypass"}) == "Green Valley Beed Bypass"


# --- AI fallback (ai.py) ---------------------------------------------------

from ai import Gemini, build_facts, check_reply, response_text  # noqa: E402
from ai import sales_topics as ai_sales_topics  # noqa: E402

AI_FAQ = parse_faq([
    {"keywords": "price, rate, area, sq ft", "answer": "SALES", "site_id": ""},
    {"keywords": "amenities, gym, pool", "answer": "{site_name} has a gym, a pool and a clubhouse.", "site_id": "GV"},
    {"keywords": "loan, home loan", "answer": "Loans from SBI and HDFC. Ask {sales_name}.", "site_id": ""},
    {"keywords": "rera", "answer": "{site_name} RERA no: P123", "site_id": "OLD"},  # inactive project: left out
])


class FakeAI:
    def __init__(self, reply="Yes, there is a gym and a pool at Green Valley Residency.", error=None):
        self.reply, self.error, self.asked = reply, error, []

    def answer(self, question, facts, topics, project="", company=""):
        self.asked.append({"question": question, "facts": facts, "topics": topics, "project": project})
        if self.error:
            raise self.error
        return self.reply


def test_ai_answers_what_the_keywords_missed():
    ai = FakeAI()
    bot, wa, store = make_bot(store=FakeStore(faq=AI_FAQ), ai=ai)
    bot.handle_message(tap("site:GV"), "Priya")
    wa.sent.clear()
    bot.handle_message(text("Kya wahan swimming karne ki jagah hai?"), "Priya")
    assert wa.kinds() == ["text"]  # an answer, no hand-off or contact card
    assert wa.sent[-1][1][1] == "Yes, there is a gym and a pool at Green Valley Residency.\n\nType MENU to see all projects."
    assert store.leads[-1][2:] == ("GV", "ai_answered", "Kya wahan swimming karne ki jagah hai?")
    asked = ai.asked[0]
    assert asked["project"] == "Green Valley Residency" and asked["topics"] == ["price", "rate", "area", "sq ft"]
    everything = " ".join(f["text"] for f in asked["facts"])
    assert "Green Valley Residency has a gym" in everything and "Loans from SBI and HDFC. Ask Office." in everything
    assert "SALES" not in everything and "P123" not in everything  # no SALES rows, no inactive projects
    assert "Priya" not in everything and "919812345678" not in everything  # nothing about the customer


def test_ai_unsure_or_failing_means_a_person_takes_over():
    for ai in (FakeAI(reply=None), FakeAI(error=TimeoutError("slow"))):
        bot, wa, store = make_bot(store=FakeStore(faq=AI_FAQ), ai=ai)
        bot.handle_message(text("Do you allow pets?"), "Ali")
        assert wa.kinds() == ["text", "contact", "list_menu"]  # the usual hand-off, menu for a newcomer
        assert store.leads[-1][3] == "handoff"


def test_ai_is_not_asked_when_the_bot_already_knows_what_to_do():
    ai = FakeAI()
    bot, wa, _ = make_bot(store=FakeStore(faq=AI_FAQ), ai=ai)
    for message in ("hi", "home loan?", "what is the rate?", "green valley"):  # menu, FAQ, SALES topic, project
        bot.handle_message(text(message), "")
    assert ai.asked == []


def test_ai_answers_are_limited_per_customer():
    ai = FakeAI()
    bot, wa, store = make_bot(store=FakeStore(faq=AI_FAQ), ai=ai)
    for i in range(11):
        bot.handle_message(text(f"question number {i}?"), "")
    events = [lead[3] for lead in store.leads]
    assert events.count("ai_answered") == 10 and events[-1] == "handoff"


def test_facts_and_sales_topics_come_from_the_sheet():
    facts = build_facts(SITES[:1], AI_FAQ, lambda answer, site: answer.replace("{site_name}", site["name"] if site else ""))
    assert [f["id"] for f in facts] == ["P1", "F1", "F2"]
    assert facts[0]["text"].startswith("Project: Green Valley Residency\nAlso called: green valley, gv")
    assert "Availability: 2BHK: 5 left" in facts[0]["text"]
    assert facts[1]["text"] == ("About Green Valley Residency. Topic: amenities, gym, pool. "
                                "Answer: Green Valley Residency has a gym, a pool and a clubhouse.")
    gv_only = parse_faq([{"keywords": "possession", "answer": "SALES", "site_id": "GV"}])
    assert ai_sales_topics(gv_only, "GV") == ["possession"] and ai_sales_topics(gv_only, "SH") == []


FACTS = [{"id": "P1", "text": "Project: Green Valley\nAvailability: 2 BHK (1,050 sq ft): 5 flats left"},
         {"id": "F1", "text": "Topic: timings. Answer: Site office open 10 am to 7 pm."}]


def gemini_reply(payload, status=200):
    """A fake Gemini endpoint that returns `payload` as the model's JSON text."""
    seen = []

    def handler(request):
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "quota"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": "Thinking about it", "thought": True},
            {"text": payload if isinstance(payload, str) else json.dumps(payload)}]}}]})

    return Gemini("KEY123", "gemini-test", http=httpx.Client(transport=httpx.MockTransport(handler))), seen


def test_gemini_request_holds_only_the_facts_and_the_question():
    gemini, seen = gemini_reply({"handoff": False, "answer": "5 flats of 2 BHK are left.", "sources": ["P1"]})
    assert gemini.answer("How many 2 BHK left?", FACTS, ["price"], "Green Valley", "Shree Builders") == \
        "5 flats of 2 BHK are left."
    request = seen[0]
    assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    assert request.headers["x-goog-api-key"] == "KEY123"
    body = json.loads(request.content)
    assert "Shree Builders" in body["systemInstruction"]["parts"][0]["text"]
    assert "sales-team topics: price" in body["systemInstruction"]["parts"][0]["text"]
    prompt = body["contents"][0]["parts"][0]["text"]
    assert "[P1] Project: Green Valley" in prompt and "[F1] Topic: timings" in prompt
    assert prompt.rstrip().endswith('How many 2 BHK left?\n"""')
    assert body["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"


def test_unsafe_or_unsure_ai_replies_are_never_sent():
    def verdict(reply):
        return check_reply(reply if isinstance(reply, str) else json.dumps(reply), FACTS)

    assert verdict({"handoff": False, "answer": "The office is open 10 am to 7 pm.", "sources": ["F1"]})[0]
    assert verdict('```json\n{"handoff": false, "answer": "1050 sq ft, 5 left.", "sources": ["P1"]}\n```')[0]
    assert verdict({"handoff": True, "answer": "", "sources": []}) == (None, "model handed off")
    assert verdict({"handoff": False, "answer": "Yes.", "sources": []})[0] is None  # no source
    assert verdict({"handoff": False, "answer": "Yes.", "sources": ["F9"]})[0] is None  # made-up source
    assert verdict({"handoff": False, "answer": "Open 9 am to 7 pm.", "sources": ["F1"]})[1] == \
        "numbers not in the cited facts: ['9']"
    assert verdict({"handoff": False, "answer": "2 BHK costs 45 lakh.", "sources": ["P1"]})[0] is None
    assert verdict({"handoff": False, "answer": "x" * 1001, "sources": ["F1"]})[0] is None
    assert verdict("Sure! The office opens at 10.")[0] is None  # not JSON
    assert response_text({"promptFeedback": {"blockReason": "SAFETY"}}) == ""

    gemini, _ = gemini_reply({}, status=429)  # quota or outage: hand off
    assert gemini.answer("timings?", FACTS, []) is None
    gemini, seen = gemini_reply({"handoff": False, "answer": "Yes.", "sources": ["F1"]})
    assert gemini.answer("timings?", [], []) is None and seen == []  # nothing to answer from: not even asked
