"""Print one X read. Does not compare a mint or write an investigation.

    uv run python -m x_intel.x_smoke https://x.com/mamesukeshow
"""

from __future__ import annotations

import argparse
import json

from x_intel.x_client import read_x


def main() -> None:
    parser = argparse.ArgumentParser(description="Read one X profile or status")
    parser.add_argument("url", help="x.com or twitter.com profile or status URL")
    args = parser.parse_args()
    print(json.dumps(read_x(args.url), indent=2))


if __name__ == "__main__":
    main()
