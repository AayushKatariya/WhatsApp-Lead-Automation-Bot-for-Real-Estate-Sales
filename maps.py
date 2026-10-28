"""Turn a Google Maps link from the Sheet into coordinates for a WhatsApp location pin."""

import logging
import re
import time
from urllib.parse import unquote, urlparse

import httpx

log = logging.getLogger("bot.maps")

_NUM = r"(-?\d{1,3}\.\d+)"
# Most exact first: the dropped pin (!3d..!4d..), then explicit coordinates, then the map's centre.
PATTERNS = [
    rf"!3d{_NUM}!4d{_NUM}",
    rf"[?&](?:q|query|ll|destination|daddr)=(?:loc:)?{_NUM}\s*,\s*\+?{_NUM}",
    rf"/(?:place|search|dir)/{_NUM}\s*,\s*\+?{_NUM}",
    rf"@{_NUM},{_NUM}",
    rf"center={_NUM},{_NUM}",
]
GOOGLE_HOSTS = ("goo.gl", "g.co", "google.com", "google.co.in")
RETRY_FAILED_AFTER = 600  # seconds


def coords_from_text(text):
    text = unquote(unquote(text or ""))
    for pattern in PATTERNS:
        m = re.search(pattern, text)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
    return None


def _is_google(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in GOOGLE_HOSTS)


class MapsResolver:
    """Reads coordinates from the link itself; opens short links (maps.app.goo.gl) to find them."""

    def __init__(self, http=None):
        self.http = http or httpx.Client(
            timeout=6, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36"},
        )
        self._found = {}
        self._failed = {}

    def coords(self, link):
        link = (link or "").strip()
        if not link:
            return None
        if link in self._found:
            return self._found[link]
        if time.time() - self._failed.get(link, 0) < RETRY_FAILED_AFTER:
            return None
        found = coords_from_text(link)
        if not found and _is_google(link):
            try:
                r = self.http.get(link)
                found = coords_from_text(str(r.url)) or coords_from_text(r.text[:500_000])
            except Exception:
                log.exception("Could not open maps link %s", link)
        if found:
            self._found[link] = found
        else:
            log.warning("No coordinates found in maps link %s; sending it as a link instead", link)
            self._failed[link] = time.time()
        return found
