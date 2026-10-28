"""Saves every WhatsApp message, delivery update and lead event to PostgreSQL for the dashboard.

Optional: without DATABASE_URL the bot uses NoHistory and works exactly as before.
A database problem is logged and never stops the bot from replying.
The tables are created by the dashboard (dashboard/db/schema.sql).
"""

import functools
import json
import logging

log = logging.getLogger("bot.history")

# Delivery updates can arrive out of order; a status only replaces a lower one.
STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}


def describe_incoming(msg):
    """Readable text of a customer's message, for previews and search."""
    kind = msg.get("type", "")
    part = msg.get(kind)
    part = part if isinstance(part, dict) else {}
    if kind == "text":
        return part.get("body", "")
    if kind == "interactive":
        reply = part.get("list_reply") or part.get("button_reply") or {}
        return reply.get("title", "")
    if kind == "button":
        return part.get("text", "")
    if kind == "location":
        return " ".join(str(part.get(k, "")) for k in ("name", "address") if part.get(k)) or \
            f"{part.get('latitude', '')}, {part.get('longitude', '')}"
    return part.get("caption", "") or part.get("filename", "")  # voice notes, photos, documents...


def describe_outgoing(msg_type, body):
    """Readable text of a message the bot sent."""
    if msg_type == "text":
        return body.get("body", "")
    if msg_type == "interactive":
        return body.get("body", {}).get("text", "")
    if msg_type == "location":
        return " ".join(body.get(k, "") for k in ("name", "address") if body.get(k))
    if msg_type == "contacts":
        card = (body or [{}])[0]
        phones = ", ".join(p.get("phone", "") for p in card.get("phones", []))
        return f"{card.get('name', {}).get('formatted_name', '')} {phones}".strip()
    return ""


def _safe(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            method(self, *args, **kwargs)
        except Exception:
            log.exception("Could not save to the database (%s)", method.__name__)
    return wrapper


class NoHistory:
    """Used when no database is configured."""

    def incoming(self, phone, name, msg):
        pass

    def outgoing(self, to, msg_type, body, wa_message_id="", error=""):
        pass

    def status(self, update):
        pass

    def event(self, phone, name, site, event, detail=""):
        pass


_UPSERT_CONTACT = """
    INSERT INTO contacts (phone, name) VALUES (%s, %s)
    ON CONFLICT (phone) DO UPDATE
    SET name = CASE WHEN EXCLUDED.name <> '' THEN EXCLUDED.name ELSE contacts.name END
"""


class History:
    def __init__(self, database_url="", pool=None):
        if pool is None:
            from psycopg_pool import ConnectionPool

            # min_size=0: nothing connects at start-up; check: drop connections the database closed while idle;
            # prepare_threshold=None: no server-side prepared statements, so Neon's pooled address works too
            pool = ConnectionPool(database_url, min_size=0, max_size=4, max_idle=120, open=True,
                                  check=ConnectionPool.check_connection, kwargs={"prepare_threshold": None})
        self.pool = pool

    def _run(self, *statements):
        with self.pool.connection() as conn:  # one transaction: committed at the end of the block
            for sql, params in statements:
                conn.execute(sql, params)

    @_safe
    def incoming(self, phone, name, msg):
        self._run(
            (_UPSERT_CONTACT + ", last_seen = now()", (phone, name)),
            ("""INSERT INTO messages (phone, direction, kind, body, payload, wa_message_id, status)
                VALUES (%s, 'in', %s, %s, %s::jsonb, %s, 'received')
                ON CONFLICT (wa_message_id) DO NOTHING""",
             (phone, msg.get("type", ""), describe_incoming(msg), json.dumps(msg), msg.get("id") or None)),
        )

    @_safe
    def outgoing(self, to, msg_type, body, wa_message_id="", error=""):
        if msg_type == "template":  # sales alerts go to salespeople, not the customer: saved as a 'sales_alerted' event
            return
        self._run((
            """INSERT INTO messages (phone, direction, kind, body, payload, wa_message_id, status, error)
               VALUES (%s, 'out', %s, %s, %s::jsonb, %s, %s, %s)""",
            (to.lstrip("+"), msg_type, describe_outgoing(msg_type, body), json.dumps(body),
             wa_message_id or None, "failed" if error else "sent", error),
        ))

    @_safe
    def status(self, update):
        """A delivery update from Meta's webhook: sent, delivered, read or failed (with the reason)."""
        status = update.get("status", "")
        if status not in STATUS_RANK or not update.get("id"):
            return
        error = "; ".join(
            " ".join(str(x) for x in (e.get("code", ""), e.get("title", ""), e.get("error_data", {}).get("details", "")) if x)
            for e in update.get("errors", [])
        )
        self._run((
            """UPDATE messages SET status = %s, error = CASE WHEN %s <> '' THEN %s ELSE error END
               WHERE wa_message_id = %s AND direction = 'out'
                 AND (CASE status WHEN 'sent' THEN 1 WHEN 'delivered' THEN 2 WHEN 'read' THEN 3
                                  WHEN 'failed' THEN 4 ELSE 0 END) < %s""",
            (status, error, error, update["id"], STATUS_RANK[status]),
        ))

    @_safe
    def event(self, phone, name, site, event, detail=""):
        self._run(
            (_UPSERT_CONTACT, (phone, name)),
            ("INSERT INTO events (phone, site_id, site_name, event, detail) VALUES (%s, %s, %s, %s, %s)",
             (phone, site["site_id"] if site else "", site["name"] if site else "", event, detail)),
        )
