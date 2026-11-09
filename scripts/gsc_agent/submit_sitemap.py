#!/usr/bin/env python3
"""Resubmit sitemap.xml to Google Search Console after a publish.

IndexNow reaches Bing, Yandex, Seznam, Naver and Yep (and through Bing, the
LLM search tools that use its index), but Google ignores IndexNow. Google has
no API for "Request indexing" outside job postings; resubmitting the sitemap
is the supported way to tell it something changed.

    GSC_SA_KEY=~/.secrets/parkingnetherlands-gsc.json python3 submit_sitemap.py

Needs the service account to hold Full (not Restricted) permission on the
property; it does as of 2026-11-09.
"""
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

PROP = os.environ.get("GSC_PROPERTY", "sc-domain:parkingnetherlands.com")
SITEMAP = "https://parkingnetherlands.com/sitemap.xml"


def main() -> int:
    key = os.path.expanduser(os.environ.get("GSC_SA_KEY", "~/.secrets/parkingnetherlands-gsc.json"))
    creds = service_account.Credentials.from_service_account_file(
        key, scopes=["https://www.googleapis.com/auth/webmasters"])
    s = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    s.sitemaps().submit(siteUrl=PROP, feedpath=SITEMAP).execute()
    sm = s.sitemaps().get(siteUrl=PROP, feedpath=SITEMAP).execute()
    print(f"sitemap resubmitted to Google: last submitted {sm.get('lastSubmitted')}, "
          f"errors {sm.get('errors')}, warnings {sm.get('warnings')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
