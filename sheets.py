"""Google Sheet 'control panel': Sites, FAQ and Messages are read; Leads is written."""

import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("bot.sheets")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
LEADS_HEADER = ["timestamp", "phone", "name", "site_id", "site_name", "event", "detail"]
IST = ZoneInfo("Asia/Kolkata")


def _yes(value):
    return str(value).strip().lower() in {"yes", "y", "true", "1", "active"}


def _float(value):
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def parse_sites(records):
    sites = []
    for r in records:
        site_id = str(r.get("site_id", "")).strip()
        name = str(r.get("name", "")).strip()
        if not site_id or not name or not _yes(r.get("active", "")):
            continue
        sites.append(
            {
                "site_id": site_id,
                "name": name,
                "aliases": [a.strip() for a in str(r.get("aliases", "")).split(",") if a.strip()],
                "tagline": str(r.get("tagline", "")).strip(),
                "brochure_url": str(r.get("brochure_url", "")).strip(),
                "brochure_filename": str(r.get("brochure_filename", "")).strip() or f"{name} brochure.pdf",
                "availability": str(r.get("availability", "")).strip(),
                "maps_link": str(r.get("maps_link", "")).strip(),
                "latitude": _float(r.get("latitude", "")),
                "longitude": _float(r.get("longitude", "")),
                "address": str(r.get("address", "")).strip(),
                "sales_name": str(r.get("sales_name", "")).strip(),
                "sales_phone": str(r.get("sales_phone", "")).strip(),
                "alert_phones": str(r.get("alert_phones", "")).strip(),
            }
        )
    return sites


def parse_faq(records):
    faq = []
    for r in records:
        keywords = [k.strip().lower() for k in str(r.get("keywords", "")).split(",") if k.strip()]
        answer = str(r.get("answer", "")).strip()
        if keywords and answer:
            faq.append({
                "keywords": keywords,
                "answer": answer,
                "site_id": str(r.get("site_id", "")).strip(),
                # the answer "SALES" means: don't answer in chat, hand the customer to a salesperson
                "to_sales": answer.upper() == "SALES",
            })
    return faq


def parse_messages(records):
    return {
        str(r.get("key", "")).strip(): str(r.get("text", "")).strip()
        for r in records
        if str(r.get("key", "")).strip() and str(r.get("text", "")).strip()
    }


class SheetStore:
    """Reads the control-panel tabs (cached for `ttl` seconds) and appends to Leads."""

    def __init__(self, sheet_id, credentials_json="", ttl=60):
        import gspread
        import google.auth
        from google.oauth2.service_account import Credentials

        if credentials_json:
            creds = Credentials.from_service_account_info(json.loads(credentials_json), scopes=SCOPES)
        else:
            # On Cloud Run this is the service's own identity: no key file needed.
            creds, _ = google.auth.default(scopes=SCOPES)
        self.book = gspread.authorize(creds).open_by_key(sheet_id)
        self.ttl = ttl
        self._cache = {}

    def _records(self, tab):
        hit = self._cache.get(tab)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        try:
            rows = self.book.worksheet(tab).get_all_records(numericise_ignore=["all"])
        except Exception:  # missing tab or a temporary Sheets error: keep the last good copy
            log.exception("Could not read tab %s", tab)
            return hit[1] if hit else []
        self._cache[tab] = (time.time(), rows)
        return rows

    def sites(self):
        return parse_sites(self._records("Sites"))

    def faq(self):
        return parse_faq(self._records("FAQ"))

    def messages(self):
        return parse_messages(self._records("Messages"))

    def log_lead(self, phone, name, site, event, detail=""):
        row = [
            datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            phone,
            name,
            site["site_id"] if site else "",
            site["name"] if site else "",
            event,
            detail,
        ]
        # RAW so a customer typing "=..." can't inject a formula into your sheet
        self.book.worksheet("Leads").append_row(row, value_input_option="RAW")

    def last_site_id(self, phone):
        """The project this customer most recently picked, from the Leads log."""
        try:
            rows = self.book.worksheet("Leads").get_all_values()
        except Exception:
            log.exception("Could not read Leads")
            return ""
        for row in reversed(rows[1:]):
            if len(row) > 3 and row[1] == phone and row[3]:
                return row[3]
        return ""
