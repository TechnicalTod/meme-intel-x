"""Read one X profile or status with the research-bot Chrome profile.

The profile directory is X_CHROME_PROFILE. It is not the FOMO login profile.
A profile read scrolls the timeline and opens a few posts so replies are part
of the evidence. This module does not follow, like, or post. A missing profile
returns UNKNOWN instead of pretending the account was read.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from x_intel.x_urls import parse_x_url

_CACHE_SECONDS = 15 * 60
_LOGIN_MARKERS = ("sign in to x", "log in to x", "sign in to twitter")
_POST_CAP = 12
_THREAD_CAP = 3
_REPLY_CAP = 8
_ARTICLES_JS = """() => {
  const rows = [];
  const seen = new Set();
  for (const article of document.querySelectorAll("article")) {
    const textNode = article.querySelector('[data-testid="tweetText"]');
    const link = article.querySelector('a[href*="/status/"]');
    const href = link ? (link.getAttribute("href") || "") : "";
    const id = (href.match(/status\\/(\\d+)/) || [])[1] || "";
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const userNode = article.querySelector('[data-testid="User-Name"]');
    const user = userNode ? userNode.innerText.split("\\n")[0] : "";
    rows.push({
      id,
      user: user.slice(0, 80),
      text: textNode ? textNode.innerText.slice(0, 500) : ""
    });
  }
  return rows;
}"""
_SHOW_MORE_JS = """() => {
  let clicks = 0;
  for (const node of document.querySelectorAll('[role="button"], button, span')) {
    if (!/show more replies|show additional replies|show replies/i.test(node.innerText || "")) continue;
    node.click();
    clicks += 1;
    if (clicks >= 3) break;
  }
}"""
_BIO_JS = """() => {
  const link = document.querySelector('[data-testid="UserUrl"] a');
  const desc = document.querySelector('[data-testid="UserDescription"]');
  return {
    bio_url: link ? link.getAttribute("href") : null,
    bio: desc ? desc.innerText.slice(0, 300) : ""
  };
}"""


def chrome_profile() -> Path | None:
    raw = os.environ.get("X_CHROME_PROFILE", "").strip()
    if not raw:
        return None
    return Path(raw)


def read_x(raw_url: str, *, timeout_s: float = 50) -> dict[str, Any]:
    """Return posts and replies. Never raises for a bad URL or a missing profile.

    This reader does not know what a mint is. The project-check repo decides
    whether the text names a contract.
    """
    parsed = parse_x_url(raw_url)
    if parsed["kind"] == "rejected":
        return _section(None, "rejected", url=parsed["url"], reason=parsed["reason"])

    handle = str(parsed["handle"])
    cached = _read_cache(handle)
    if cached is not None:
        cached["from_cache"] = True
        return cached

    profile = chrome_profile()
    if profile is None or not profile.exists():
        return _section(handle, "UNKNOWN", url=parsed["url"], reason="no_profile")

    try:
        observed = _read_with_playwright(parsed, profile, timeout_s)
    except Exception as exc:  # browser missing or the page never settled
        return _section(handle, "UNKNOWN", url=parsed["url"], reason=type(exc).__name__)

    status = "BLOCKED" if observed["blocked"] else "ok"
    section = _section(
        handle,
        status,
        bio=observed["text"],
        bio_url=observed["bio_url"],
        posts=observed.get("posts") or [],
        url=parsed["url"],
        reason=observed["reason"],
    )
    if status == "ok":
        _write_cache(handle, section)
    return section


def _section(
    handle: str | None,
    status: str,
    *,
    bio: str = "",
    bio_url: str | None = None,
    posts: list | None = None,
    url: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "handle": handle,
        "status": status,
        "bio_url": bio_url,
        "text_excerpt": (bio or "")[:500],
        "posts": list(posts or []),
        "url": url,
        "reason": reason,
    }


def _read_with_playwright(parsed: dict[str, Any], profile: Path, timeout_s: float) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    deadline = time.monotonic() + timeout_s
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile),
            channel="chrome",
            headless=True,
            viewport={"width": 1280, "height": 900},
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--no-first-run"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            if not _goto(page, str(parsed["url"]), deadline):
                return _empty("timeout")
            _wait_for_articles(page, min(deadline, time.monotonic() + 8))
            if _login_wall(page):
                return _empty("login_wall", blocked=True)
            bio = page.evaluate(_BIO_JS)
            if parsed["kind"] == "status" and parsed.get("status_id"):
                posts = _thread(page, str(parsed["status_id"]), deadline)
            else:
                posts = _timeline(page, str(parsed["handle"]), deadline)
            return {
                "text": "" if not bio else (bio.get("bio") or ""),
                "bio_url": bio.get("bio_url") if bio else None,
                "posts": posts,
                "blocked": False,
                "reason": None if posts else "no_posts",
            }
        finally:
            context.close()


def _empty(reason: str, *, blocked: bool = False) -> dict[str, Any]:
    return {"text": "", "bio_url": None, "posts": [], "blocked": blocked, "reason": reason}


def _goto(page: Any, url: str, deadline: float) -> bool:
    left = deadline - time.monotonic()
    if left < 5:
        return False
    page.goto(url, wait_until="domcontentloaded", timeout=int(min(left, 20) * 1000))
    return True


def _wait_for_articles(page: Any, deadline: float) -> None:
    while time.monotonic() < deadline:
        if page.evaluate("() => document.querySelectorAll('article').length"):
            return
        page.wait_for_timeout(400)


def _login_wall(page: Any) -> bool:
    if page.evaluate("() => document.querySelectorAll('article').length"):
        return False
    body = page.inner_text("body").lower()
    return any(marker in body for marker in _LOGIN_MARKERS)


def _timeline(page: Any, handle: str, deadline: float) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    stuck = 0
    while time.monotonic() < deadline and len(seen) < _POST_CAP:
        before = len(seen)
        _absorb(page, seen, _POST_CAP)
        if len(seen) >= _POST_CAP:
            break
        if len(seen) == before:
            stuck += 1
            if stuck >= 3:
                break
        else:
            stuck = 0
        page.evaluate("window.scrollBy(0, 1600)")
        page.wait_for_timeout(800)
    posts = list(seen.values())
    for post in posts[:_THREAD_CAP]:
        if deadline - time.monotonic() < 8:
            break
        if not _goto(page, f"https://x.com/{handle}/status/{post['id']}", deadline):
            break
        _wait_for_articles(page, min(deadline, time.monotonic() + 6))
        post["replies"] = _replies(page, post["id"])
    return posts


def _thread(page: Any, status_id: str, deadline: float) -> list[dict[str, Any]]:
    _wait_for_articles(page, min(deadline, time.monotonic() + 6))
    seen: dict[str, dict[str, Any]] = {}
    _absorb(page, seen, 1)
    post = seen.get(status_id) or (list(seen.values())[0] if seen else None)
    if post is None:
        return []
    post["replies"] = _replies(page, post["id"])
    return [post]


def _replies(page: Any, root_id: str) -> list[dict[str, Any]]:
    page.evaluate(_SHOW_MORE_JS)
    page.wait_for_timeout(700)
    page.evaluate("window.scrollBy(0, 1800)")
    page.wait_for_timeout(700)
    seen: dict[str, dict[str, Any]] = {}
    _absorb(page, seen, _REPLY_CAP + 8)
    seen.pop(root_id, None)
    replies = [row for row in seen.values() if row["text"]]
    for row in replies:
        row.pop("replies", None)
    return replies[:_REPLY_CAP]


def _absorb(page: Any, seen: dict[str, dict[str, Any]], cap: int) -> None:
    for raw in page.evaluate(_ARTICLES_JS):
        status_id = str(raw.get("id") or "")
        text = str(raw.get("text") or "").strip()
        if not status_id or not text or status_id in seen:
            continue
        seen[status_id] = {
            "id": status_id,
            "user": str(raw.get("user") or "").strip()[:80],
            "text": text[:500],
            "replies": [],
        }
        if len(seen) >= cap:
            return


def _cache_file(handle: str) -> Path | None:
    try:
        raw = os.environ.get("X_DATA_DIR", "/var/lib/meme-intel-x").strip() or "/var/lib/meme-intel-x"
        root = Path(raw) / "x_cache"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{handle.lower()}.json"
    except OSError:
        return None


def _read_cache(handle: str) -> dict[str, Any] | None:
    path = _cache_file(handle)
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(payload["fetched_at"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None
    age = datetime.now(timezone.utc) - fetched
    if age.total_seconds() > _CACHE_SECONDS:
        return None
    body = payload.get("section")
    return body if isinstance(body, dict) else None


def _write_cache(handle: str, section: dict[str, Any]) -> None:
    path = _cache_file(handle)
    if path is None:
        return
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "section": section,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
