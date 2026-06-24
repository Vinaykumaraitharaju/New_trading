from __future__ import annotations

from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from functools import lru_cache
import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import requests


_POSITIVE_PATTERNS: tuple[tuple[str, int], ...] = (
    ("target raised", 3),
    ("price target raised", 3),
    ("upgrade", 3),
    ("buy call", 3),
    ("bullish", 3),
    ("beats", 3),
    ("beat", 2),
    ("profit jumps", 3),
    ("profit rises", 2),
    ("surges", 2),
    ("jumps", 2),
    ("rallies", 2),
    ("gains", 1),
    ("wins", 2),
    ("order win", 3),
    ("secures order", 3),
    ("partnership", 2),
    ("approval", 2),
    ("dividend", 1),
    ("rebound", 1),
    ("growth", 1),
    ("strong", 1),
)

_NEGATIVE_PATTERNS: tuple[tuple[str, int], ...] = (
    ("price target cut", -3),
    ("target cut", -3),
    ("downgrade", -3),
    ("sell call", -3),
    ("bearish", -3),
    ("misses", -3),
    ("miss", -2),
    ("warning", -2),
    ("probe", -3),
    ("penalty", -3),
    ("fraud", -4),
    ("lawsuit", -3),
    ("slumps", -3),
    ("plunges", -3),
    ("tumbles", -3),
    ("falls", -2),
    ("drops", -2),
    ("declines", -2),
    ("down", -1),
    ("weak", -1),
    ("loss", -2),
    ("block deal", -1),
    ("stake sale", -1),
    ("delay", -1),
)

_NEUTRAL_PATTERNS: tuple[str, ...] = (
    "to announce",
    "results date",
    "earnings expectations",
    "record date",
    "board meeting",
    "date and time",
    "q4 results",
    "q1 results",
)


@dataclass(frozen=True)
class StockHeadline:
    title: str
    publisher: str = ""
    link: str = ""
    published_at: str = ""
    direction: str = "Neutral"
    sentiment_score: float = 0.0


@dataclass(frozen=True)
class StockNewsSnapshot:
    direction: str = "Neutral"
    bias: str = "neutral"
    summary: str = "No fresh stock-specific headlines were fetched."
    source: str = "Google News RSS"
    confidence_pct: int = 0
    score_adjustment: float = 0.0
    latest_headline: str = ""
    headlines: list[StockHeadline] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _headline_score(title: str) -> int:
    lowered = _normalize_text(title).lower()
    if not lowered:
        return 0
    if any(pattern in lowered for pattern in _NEUTRAL_PATTERNS):
        return 0
    score = 0
    for pattern, weight in _POSITIVE_PATTERNS:
        if pattern in lowered:
            score += weight
    for pattern, weight in _NEGATIVE_PATTERNS:
        if pattern in lowered:
            score += weight
    return score


def _direction_for_score(score: float) -> tuple[str, str]:
    if score >= 2:
        return "Bullish", "bullish"
    if score <= -2:
        return "Sell", "sell"
    return "Neutral", "neutral"


def _safe_published_at(raw_value: str) -> str:
    text = _normalize_text(raw_value)
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).strftime("%d %b %H:%M")
    except (TypeError, ValueError, OverflowError):
        return text


def _query_text(symbol: str, company_name: str) -> str:
    clean_symbol = str(symbol or "").upper().strip()
    clean_name = _normalize_text(company_name)
    parts = [part for part in [f'"{clean_name}"' if clean_name and clean_name.upper() != clean_symbol else "", clean_symbol] if part]
    joined = " OR ".join(parts) if parts else clean_symbol
    return f"({joined}) stock OR share OR NSE OR BSE"


class StockNewsService:
    """Fetch recent stock-specific headlines and infer a simple direction read."""

    def __init__(self, timeout: float = 6.0, max_headlines: int = 5) -> None:
        self.timeout = timeout
        self.max_headlines = max(1, max_headlines)

    def fetch(self, symbol: str, company_name: str = "") -> StockNewsSnapshot:
        return _fetch_cached(str(symbol or "").upper().strip(), _normalize_text(company_name), self.max_headlines, self.timeout)


@lru_cache(maxsize=256)
def _fetch_cached(symbol: str, company_name: str, max_headlines: int, timeout: float) -> StockNewsSnapshot:
    if not symbol:
        return StockNewsSnapshot(summary="Stock symbol is missing, so stock-news direction cannot be computed.")

    params = {
        "q": _query_text(symbol, company_name),
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
    }
    url = "https://news.google.com/rss/search?" + urlencode(params)
    session = requests.Session()
    session.trust_env = False

    try:
        response = session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception as exc:
        return StockNewsSnapshot(
            summary="Live stock-news feed is unavailable right now; direction is treated as neutral.",
            warnings=["Could not reach stock-news feed; confirm news manually before execution."],
            error=str(exc),
        )

    headlines: list[StockHeadline] = []
    positives: list[str] = []
    negatives: list[str] = []
    seen_titles: set[str] = set()

    for item in root.findall(".//item"):
        title = _normalize_text(item.findtext("title"))
        if not title:
            continue
        plain_title = title.split(" - ")[0].strip() or title
        unique_key = plain_title.lower()
        if unique_key in seen_titles:
            continue
        seen_titles.add(unique_key)
        score = _headline_score(plain_title)
        direction, _ = _direction_for_score(score)
        publisher = _normalize_text(item.findtext("source")) or title.rsplit(" - ", 1)[-1] if " - " in title else ""
        published_at = _safe_published_at(item.findtext("pubDate"))
        headlines.append(
            StockHeadline(
                title=plain_title,
                publisher=publisher,
                link=_normalize_text(item.findtext("link")),
                published_at=published_at,
                direction=direction,
                sentiment_score=float(score),
            )
        )
        if score >= 2:
            positives.append(plain_title)
        elif score <= -2:
            negatives.append(plain_title)
        if len(headlines) >= max_headlines:
            break

    if not headlines:
        return StockNewsSnapshot(
            summary="No recent stock-specific headlines were found; direction is neutral until fresh news appears.",
            warnings=["No fresh headlines found for this stock."],
        )

    weighted_score = 0.0
    for idx, headline in enumerate(headlines):
        weight = max(0.45, 1.0 - idx * 0.18)
        weighted_score += headline.sentiment_score * weight

    direction, bias = _direction_for_score(weighted_score)
    confidence_pct = min(92, max(32, int(36 + abs(weighted_score) * 12 + len(headlines) * 4)))
    score_adjustment = round(max(-4.0, min(4.0, weighted_score / 2.2)), 1)
    latest = headlines[0]

    if direction == "Bullish":
        summary = f"{len(headlines)} recent headlines lean bullish for {symbol}; price follow-through still matters."
    elif direction == "Sell":
        summary = f"{len(headlines)} recent headlines lean negative for {symbol}; downside pressure risk is higher."
    else:
        summary = f"Recent headlines for {symbol} are mixed, so news direction stays neutral."

    warnings = []
    if negatives:
        warnings.append("Negative headlines are present; avoid chasing weak price action.")
    elif direction == "Neutral":
        warnings.append("News flow is mixed; let price confirm before acting.")

    return StockNewsSnapshot(
        direction=direction,
        bias=bias,
        summary=summary,
        confidence_pct=confidence_pct,
        score_adjustment=score_adjustment,
        latest_headline=latest.title,
        headlines=headlines,
        positives=positives[:3],
        negatives=negatives[:3],
        warnings=warnings,
    )
