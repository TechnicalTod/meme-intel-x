"""X URL parsing and the missing-profile path. No browser."""

from __future__ import annotations

import os
import unittest

from x_intel.x_client import read_x
from x_intel.x_urls import parse_x_url, website_candidate_ok


class ParseTest(unittest.TestCase):
    def test_status_url_keeps_the_handle_and_id(self) -> None:
        parsed = parse_x_url(
            "https://x.com/matthewabides/status/2106506213458341960?s=20"
        )
        self.assertEqual(parsed["kind"], "status")
        self.assertEqual(parsed["handle"], "matthewabides")
        self.assertEqual(parsed["status_id"], "2106506213458341960")

    def test_twitter_host_becomes_a_profile(self) -> None:
        parsed = parse_x_url("https://twitter.com/mamesukeshow")
        self.assertEqual(parsed["kind"], "profile")
        self.assertEqual(parsed["url"], "https://x.com/mamesukeshow")

    def test_search_and_community_are_rejected(self) -> None:
        search = parse_x_url("https://x.com/search?q=Pirate")
        community = parse_x_url("https://x.com/i/communities/2034659076592832917")
        self.assertEqual(search["reason"], "search_or_community")
        self.assertEqual(community["reason"], "search_or_community")
        self.assertFalse(website_candidate_ok(search["url"] or ""))
        self.assertFalse(website_candidate_ok("https://x.com/mamesukeshow"))

    def test_a_normal_site_is_still_a_website(self) -> None:
        self.assertTrue(website_candidate_ok("https://themamesuke.com/"))


class ClientTest(unittest.TestCase):
    def test_missing_profile_is_unknown(self) -> None:
        os.environ.pop("X_CHROME_PROFILE", None)
        section = read_x("https://x.com/mamesukeshow")
        self.assertEqual(section["status"], "UNKNOWN")
        self.assertEqual(section["reason"], "no_profile")
        self.assertEqual(section["posts"], [])
        self.assertNotIn("x_names_address", section)
