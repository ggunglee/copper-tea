from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

from app.providers.base import EventData, NewsProvider
from app.providers.mock_provider import MockNewsProvider


QUERIES = {
    "copper": "copper supply disruption mine strike inventory",
    "uranium": "uranium supply nuclear fuel mine disruption",
    "natural_gas": "natural gas supply LNG inventory weather",
    "crude_oil": "crude oil supply OPEC sanctions disruption",
    "aluminum": "aluminum supply smelter disruption inventory",
    "lithium": "lithium supply battery material price mine",
    "nickel": "nickel supply battery metal mine disruption",
    "fertilizer": "fertilizer supply potash ammonia gas export",
    "gold": "gold price safe haven central bank",
    "silver": "silver supply demand industrial price",
    "iron_ore": "iron ore supply China steel demand",
    "steel": "steel price demand supply mill",
    "rare_earths": "rare earth supply export restriction China",
    "coal": "coal supply demand export weather",
}

EVENT_KEYWORDS = {
    "strike": 10,
    "disruption": 10,
    "sanction": 10,
    "ban": 8,
    "export": 6,
    "shortage": 10,
    "inventory": 6,
    "stockpile": 6,
    "mine": 5,
    "closure": 9,
    "weather": 5,
    "war": 8,
    "tariff": 6,
    "demand": 4,
    "surge": 6,
}

STRUCTURAL_KEYWORDS = {
    "ban",
    "closure",
    "conflict",
    "curb",
    "disruption",
    "embargo",
    "export",
    "import",
    "inventory",
    "mine",
    "policy",
    "quota",
    "sanction",
    "shortage",
    "strike",
    "supply",
    "tariff",
    "war",
}

TEMPORARY_KEYWORDS = {
    "forecast",
    "profit taking",
    "technical",
}


class RssNewsProvider(NewsProvider):
    def __init__(self, lookback_hours: int = 48) -> None:
        self.lookback = timedelta(hours=lookback_hours)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.fallback = MockNewsProvider()

    def events(self, commodity_codes: list[str]) -> list[EventData]:
        events = []
        fallback = {event.commodity_code: event for event in self.fallback.events(commodity_codes)}
        for code in commodity_codes:
            try:
                event = self._event_for_commodity(code)
            except requests.RequestException:
                event = None
            except ET.ParseError:
                event = None
            events.append(event or fallback.get(code) or EventData(code, "no_news", "bullish", 0, ""))
        return [event for event in events if event.severity >= 35]

    def _event_for_commodity(self, code: str) -> EventData | None:
        query = QUERIES.get(code, code)
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        cutoff = datetime.now(timezone.utc) - self.lookback
        articles = []
        keyword_score = 0
        structural_score = 0
        for item in root.findall("./channel/item"):
            title = unescape(item.findtext("title") or "").strip()
            link = item.findtext("link") or ""
            published = _parse_date(item.findtext("pubDate"))
            if not title or published < cutoff:
                continue
            lowered = title.lower()
            keyword_score += sum(weight for word, weight in EVENT_KEYWORDS.items() if word in lowered)
            if not any(word in lowered for word in TEMPORARY_KEYWORDS):
                structural_score += sum(1 for word in STRUCTURAL_KEYWORDS if word in lowered)
            articles.append((title, link))
            if len(articles) >= 8:
                break

        if not articles:
            return None
        severity = min(95, 40 + len(articles) * 6 + keyword_score)
        return EventData(
            commodity_code=code,
            event_type="structural_news" if structural_score else "rss_news",
            direction="bullish",
            severity=float(severity),
            title=articles[0][0],
            source="google_news_rss",
            url=articles[0][1],
        )


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
