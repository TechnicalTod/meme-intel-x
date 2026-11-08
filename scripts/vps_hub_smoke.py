"""VPS smoke: FOMO card for hub mints, then meme-intel-x read for each twitter URL.

Run on Netcup as telegramforward with /opt/meme-intel/.env sourced.
"""

from __future__ import annotations

import json
import os
import sys

SOLANA = "1399811149"


def _mint_from_argv() -> list[str]:
    if len(sys.argv) > 1:
        return sys.argv[1:]
    return [
        "SCGBBnSwnekytGFHgyeHHxPMiN7xDxsWFGg9JgFSTNK",
        "6mXFCoZ515w37YfmwXGJMPfQfiK5tr9WkihW3oN9pump",
    ]


def fomo_socials(mint: str) -> dict:
    from fomo_intel.session import Session
    from fomo_intel.tokens.paths import filter_tokens_body

    session = Session()
    path, body = filter_tokens_body(f"{mint}:{SOLANA}")
    envelope = session.post(path, body)
    rows = envelope.get("responseObject") or []
    if not rows:
        return {"mint": mint, "fomo_ok": False, "reason": "empty_response"}
    row = rows[0] if isinstance(rows, list) else rows
    token = row.get("token") if isinstance(row, dict) else {}
    socials = (token or {}).get("socialLinks") or {}
    return {
        "mint": mint,
        "fomo_ok": True,
        "symbol": (token or {}).get("symbol"),
        "website": socials.get("website"),
        "twitter": socials.get("twitter"),
        "telegram": socials.get("telegram"),
    }


def x_read(url: str | None) -> dict | None:
    if not url:
        return None
    from x_intel.x_client import read_x

    section = read_x(url, timeout_s=55)
    return {
        "url": url,
        "status": section.get("status"),
        "handle": section.get("handle"),
        "reason": section.get("reason"),
        "posts": len(section.get("posts") or []),
        "replies": sum(len(p.get("replies") or []) for p in (section.get("posts") or [])),
    }


def main() -> None:
    os.environ.setdefault("FOMO_SESSION", "auto")
    out: list[dict] = []
    for mint in _mint_from_argv():
        card = fomo_socials(mint)
        x = x_read(card.get("twitter"))
        card["x"] = x
        out.append(card)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
