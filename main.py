"""Webhook server for the WhatsApp lead bot. Settings come from environment variables."""

import hashlib
import hmac
import json
import logging
import os

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from ai import DEFAULT_MODEL, Gemini
from bot import Bot
from history import History, NoHistory
from sheets import SheetStore
from whatsapp import WhatsApp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot.main")


def env(name, default=""):
    return os.environ.get(name, default).strip()


VERIFY_TOKEN = env("WA_VERIFY_TOKEN")
APP_SECRET = env("WA_APP_SECRET")
COMPANY = env("COMPANY_NAME", "our company")

app = FastAPI()
_bot = None


def get_bot():
    """Created on first use so the server starts (and Meta can verify the webhook) even before the sheet is shared."""
    global _bot
    if _bot is None:
        # optional: with DATABASE_URL every message is also saved for the dashboard
        history = History(env("DATABASE_URL")) if env("DATABASE_URL") else NoHistory()
        _bot = Bot(
            wa=WhatsApp(env("WA_TOKEN"), env("WA_PHONE_NUMBER_ID"), env("GRAPH_API_VERSION", "v26.0"),
                        on_sent=history.outgoing),
            history=history,
            # optional: with GEMINI_API_KEY, questions the FAQ keywords miss get an AI answer from the Sheet
            ai=Gemini(env("GEMINI_API_KEY"), env("GEMINI_MODEL", DEFAULT_MODEL)) if env("GEMINI_API_KEY") else None,
            store=SheetStore(env("SHEET_ID"), env("GOOGLE_CREDENTIALS_JSON")),
            company=COMPANY,
            default_sales_name=env("DEFAULT_SALES_NAME", f"{COMPANY} Sales"),
            default_sales_phone=env("DEFAULT_SALES_PHONE"),
            alert_template=env("SALES_ALERT_TEMPLATE"),
            alert_language=env("SALES_ALERT_LANGUAGE", "en"),
            default_alert_phones=env("DEFAULT_ALERT_PHONES"),
            alert_on=env("SALES_ALERT_ON", "handoffs"),
        )
    return _bot


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/webhook")
def verify(request: Request):
    """Meta calls this once when you save the webhook URL in the App Dashboard."""
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and VERIFY_TOKEN and q.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(q.get("hub.challenge", ""))
    return Response(status_code=403)


def signature_ok(body, header):
    if not APP_SECRET:
        return True
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


@app.post("/webhook")
async def receive(request: Request):
    body = await request.body()
    if not signature_ok(body, request.headers.get("X-Hub-Signature-256")):
        log.warning("Rejected a webhook with a bad signature")
        return Response(status_code=403)
    try:
        payload = json.loads(body)
        await run_in_threadpool(get_bot().handle_webhook, payload)
    except Exception:
        # Still answer 200: a failure here would make Meta resend the same message for hours.
        log.exception("Failed to handle webhook")
    return {"status": "received"}
