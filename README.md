# meme-intel-x

Reads public X profiles and posts with a logged-in research-bot Chrome profile. It does not follow, like, or post, and it does not decide whether a post names a token contract. That comparison lives in meme-intel-check.

```bash
uv sync
uv run python -m x_intel.x_smoke https://x.com/mamesukeshow
```

On the VPS the profile is `/var/lib/fomo-intel/chrome-profile-x-diligence`, owned by `telegramforward`, mode `700`. It is not the FOMO Privy profile.

```text
X_CHROME_PROFILE=/var/lib/fomo-intel/chrome-profile-x-diligence
X_DATA_DIR=/var/lib/meme-intel-x
```

A profile read scrolls until it has 12 posts, then opens the first 3 and keeps up to 8 replies on each. The budget is 50 seconds. Results cache for 15 minutes under `X_DATA_DIR`. `status` is `ok`, `BLOCKED` when X shows a login wall, or `UNKNOWN` when the profile is missing.
