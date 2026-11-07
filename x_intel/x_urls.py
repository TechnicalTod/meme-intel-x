"""Turn an X or Twitter URL into a handle and, when present, a status id.

Search pages and community links are not profiles. A project "website" that is
only one of those is rejected so it is not crawled as a site.
"""

from __future__ import annotations

from urllib.parse import urlparse

_HOSTS = {"x.com", "twitter.com", "mobile.twitter.com", "mobile.x.com"}
_RESERVED = frozenset(
    {
        "compose",
        "explore",
        "hashtag",
        "home",
        "i",
        "intent",
        "jobs",
        "login",
        "messages",
        "notifications",
        "privacy",
        "search",
        "settings",
        "share",
        "signup",
        "tos",
    }
)


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _parts(url: str) -> list[str]:
    path = urlparse(url).path or ""
    return [part for part in path.split("/") if part]


def parse_x_url(raw: str) -> dict[str, str | None]:
    """Classify one URL. `kind` is profile, status, or rejected."""
    text = (raw or "").strip()
    if not text:
        return _rejected(text, "empty")
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if _host(text) not in _HOSTS:
        return _rejected(text, "not_x")
    parts = _parts(text)
    if not parts:
        return _rejected(text, "no_path")
    if parts[0] == "search" or (len(parts) >= 2 and parts[0] == "i" and parts[1] == "communities"):
        return _rejected(_canonical(text), "search_or_community")
    if parts[0] in _RESERVED or parts[0].startswith("i"):
        return _rejected(_canonical(text), "reserved")
    handle = parts[0].lstrip("@")
    if not handle or handle.lower() in _RESERVED:
        return _rejected(_canonical(text), "reserved")
    if len(parts) >= 3 and parts[1] == "status" and parts[2].isdigit():
        status_id = parts[2]
        url = f"https://x.com/{handle}/status/{status_id}"
        return {
            "ok": "true",
            "kind": "status",
            "handle": handle,
            "status_id": status_id,
            "url": url,
            "reason": None,
        }
    url = f"https://x.com/{handle}"
    return {
        "ok": "true",
        "kind": "profile",
        "handle": handle,
        "status_id": None,
        "url": url,
        "reason": None,
    }


def website_candidate_ok(raw: str) -> bool:
    """False for any X URL. Profiles go to the X reader; search pages are dropped."""
    return parse_x_url(raw)["reason"] == "not_x"


def _canonical(url: str) -> str:
    parsed = urlparse(url)
    return f"https://{_host(url)}{parsed.path or '/'}"


def _rejected(url: str, reason: str) -> dict[str, str | None]:
    return {
        "ok": "false",
        "kind": "rejected",
        "handle": None,
        "status_id": None,
        "url": url or None,
        "reason": reason,
    }
