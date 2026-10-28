"""Thin wrapper around the WhatsApp Cloud API send endpoint."""

import logging
import re
import threading
import time

import httpx

log = logging.getLogger("bot.whatsapp")

BROCHURE_MAX_BYTES = 100 * 1024 * 1024  # WhatsApp's document limit
BROCHURE_CACHE_SECONDS = 6 * 3600       # re-upload after 6 h, so a replaced brochure shows up (media ids last 30 days)

# WhatsApp limits for interactive messages
LIST_MAX_ROWS = 10
ROW_TITLE_MAX = 24
ROW_DESC_MAX = 72
BUTTON_TITLE_MAX = 20
HEADER_MAX = 60
FOOTER_MAX = 60
BODY_MAX = 1024


def clip(text, limit):
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def e164(phone, default_country="91"):
    """'98765 43210' -> '+919876543210'. Returns '' if there are no digits."""
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    if len(digits) == 10:
        digits = default_country + digits
    return "+" + digits


def direct_download_url(url):
    """Turn a Google Drive 'share' link into a direct-download link WhatsApp can fetch."""
    url = (url or "").strip()
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:.*&)?id=)([\w-]+)", url)
    if m:
        return f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download"
    return url


def pdf_filename(name):
    """The name customers see. Always ends in .pdf, or phones may show the file as .bin."""
    name = (name or "").strip() or "brochure"
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


class WhatsApp:
    def __init__(self, token, phone_number_id, api_version="v26.0", http=None, on_sent=None, downloader=None):
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.media_url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/media"
        self.http = http or httpx.Client(
            timeout=15, headers={"Authorization": f"Bearer {token}"}
        )
        # A separate client for fetching brochures: Google Drive (or any host) must never see the WhatsApp token
        self.downloader = downloader or httpx.Client(timeout=60, follow_redirects=True)
        # on_sent(to, msg_type, body, message_id, error) runs after every message (History.outgoing)
        self.on_sent = on_sent
        self._media = {}                # brochure url -> (WhatsApp media id, uploaded at)
        self._media_locks = {}          # one upload at a time per brochure
        self._locks_guard = threading.Lock()

    # --- brochures -----------------------------------------------------

    def brochure_media_id(self, url, filename):
        """Uploads the brochure to WhatsApp as a PDF and returns its media id ("" if that fails).

        Sent as a plain link, WhatsApp takes the file type from the host's reply, and Google Drive
        answers "application/octet-stream", which phones show as a .bin file. Uploading it ourselves
        with type application/pdf avoids that. The id is reused for BROCHURE_CACHE_SECONDS.
        """
        url = direct_download_url(url)
        with self._locks_guard:
            lock = self._media_locks.setdefault(url, threading.Lock())
        with lock:
            hit = self._media.get(url)
            if hit and time.time() - hit[1] < BROCHURE_CACHE_SECONDS:
                return hit[0]
            try:
                data = self._download_pdf(url)
                r = self.http.post(
                    self.media_url,
                    data={"messaging_product": "whatsapp", "type": "application/pdf"},
                    files={"file": (pdf_filename(filename), data, "application/pdf")},
                    timeout=120,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"WhatsApp media upload error {r.status_code}: {r.text[:300]}")
                media_id = r.json()["id"]
            except Exception as error:
                log.warning("Brochure %s not uploaded, sending it as a link instead: %s", url, error)
                return ""
            self._media[url] = (media_id, time.time())
            return media_id

    def _download_pdf(self, url):
        size, chunks = 0, []
        with self.downloader.stream("GET", url) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"download failed with HTTP {r.status_code}")
            for chunk in r.iter_bytes():
                size += len(chunk)
                if size > BROCHURE_MAX_BYTES:
                    raise RuntimeError("the file is over WhatsApp's 100 MB limit")
                chunks.append(chunk)
        data = b"".join(chunks)
        if not data.startswith(b"%PDF"):
            # Google Drive sends a web page instead when the file isn't shared with "Anyone with the link",
            # is over 100 MB (virus-scan warning) or has hit its download limit
            raise RuntimeError("the link didn't return a PDF; check it's shared as 'Anyone with the link'")
        return data

    def _post(self, payload):
        payload = {"messaging_product": "whatsapp", **payload}
        r = self.http.post(self.url, json=payload)
        if r.status_code >= 400:
            log.error("WhatsApp API error %s: %s", r.status_code, r.text)
        return r

    def _send(self, to, msg_type, body):
        r = self._post({"recipient_type": "individual", "to": to, "type": msg_type, msg_type: body})
        if self.on_sent:
            message_id, error = "", ""
            if r.status_code >= 400:
                error = f"WhatsApp API error {r.status_code}: {r.text[:500]}"
            else:
                try:
                    message_id = r.json()["messages"][0]["id"]
                except Exception:
                    pass
            self.on_sent(to, msg_type, body, message_id, error)
        return r

    # --- message types -------------------------------------------------

    def mark_read(self, message_id):
        return self._post({"status": "read", "message_id": message_id})

    def text(self, to, body):
        return self._send(to, "text", {"body": body, "preview_url": True})

    def list_menu(self, to, header, body, footer, button, rows):
        """rows: [(id, title, description), ...] - only the first 10 are sent."""
        section_rows = [
            {"id": rid, "title": clip(title, ROW_TITLE_MAX), "description": clip(desc, ROW_DESC_MAX)}
            for rid, title, desc in rows[:LIST_MAX_ROWS]
        ]
        for row in section_rows:
            if not row["description"]:
                del row["description"]
        interactive = {
            "type": "list",
            "body": {"text": clip(body, BODY_MAX)},
            "action": {"button": clip(button, BUTTON_TITLE_MAX), "sections": [{"title": "Projects", "rows": section_rows}]},
        }
        if header:
            interactive["header"] = {"type": "text", "text": clip(header, HEADER_MAX)}
        if footer:
            interactive["footer"] = {"text": clip(footer, FOOTER_MAX)}
        return self._send(to, "interactive", interactive)

    def buttons(self, to, body, buttons, header_text="", document_url="", document_filename=""):
        """buttons: [(id, title), ...] - WhatsApp allows at most 3.

        With document_url the PDF rides on top of the message as its header, so
        brochure, text and buttons always arrive together, as one message.
        """
        interactive = {
            "type": "button",
            "body": {"text": clip(body, BODY_MAX)},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": bid, "title": clip(title, BUTTON_TITLE_MAX)}}
                    for bid, title in buttons[:3]
                ]
            },
        }
        if document_url:
            media_id = self.brochure_media_id(document_url, document_filename)
            document = {"id": media_id} if media_id else {"link": direct_download_url(document_url)}
            document["filename"] = pdf_filename(document_filename)
            interactive["header"] = {"type": "document", "document": document}
        elif header_text:
            interactive["header"] = {"type": "text", "text": clip(header_text, HEADER_MAX)}
        return self._send(to, "interactive", interactive)

    def location(self, to, latitude, longitude, name, address):
        return self._send(
            to,
            "location",
            {"latitude": latitude, "longitude": longitude, "name": name, "address": address},
        )

    def contact(self, to, name, phone):
        number = e164(phone)
        return self._send(
            to,
            "contacts",
            [
                {
                    "name": {"formatted_name": name, "first_name": name},
                    "phones": [{"phone": number, "type": "WORK", "wa_id": number.lstrip("+")}],
                }
            ],
        )

    def template(self, to, name, language, params):
        """Send an approved template whose body has {{1}}..{{n}} text variables."""
        return self._send(
            to,
            "template",
            {
                "name": name,
                "language": {"code": language},
                "components": [
                    {
                        "type": "body",
                        # template variables may not contain newlines or long runs of spaces
                        "parameters": [{"type": "text", "text": clip(re.sub(r"\s+", " ", str(p)), 300) or "-"} for p in params],
                    }
                ],
            },
        )
