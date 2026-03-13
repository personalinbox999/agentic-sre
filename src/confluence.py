"""
confluence.py — Fetches runbook pages from Confluence Cloud and ingests them into Qdrant.

All credentials are loaded from .env:
  CONFLUENCE_BASE_URL    https://personalinbox999.atlassian.net
  CONFLUENCE_USER_EMAIL  personalinbox999@gmail.com
  CONFLUENCE_API_KEY     <API token>
  CONFLUENCE_SPACE_KEY   MFS
"""

import os
import re
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

CONFLUENCE_BASE_URL  = os.getenv("CONFLUENCE_BASE_URL", "")
CONFLUENCE_EMAIL     = os.getenv("CONFLUENCE_USER_EMAIL", "")
CONFLUENCE_API_KEY   = os.getenv("CONFLUENCE_API_KEY", "")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY", "MFS")

_auth = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_KEY)
_headers = {"Accept": "application/json"}


def _strip_html(html: str) -> str:
    """Very lightweight HTML tag stripper — no external deps needed."""
    return re.sub(r"<[^>]+>", " ", html).strip()


def get_all_pages(space_key: str = CONFLUENCE_SPACE_KEY, limit: int = 50) -> list[dict]:
    """
    Returns a list of dicts with keys: id, title, body (plain text).
    Paginates automatically up to `limit` pages.
    """
    url = f"{CONFLUENCE_BASE_URL}/wiki/rest/api/content"
    params = {
        "spaceKey": space_key,
        "type": "page",
        "expand": "body.storage",
        "limit": 25,
        "start": 0,
    }

    pages = []
    while len(pages) < limit:
        resp = requests.get(url, headers=_headers, auth=_auth, params=params)
        if not resp.ok:
            print(f"[ConfluenceAPI] Error {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        for page in results:
            body_html = page.get("body", {}).get("storage", {}).get("value", "")
            plain_text = _strip_html(body_html)
            pages.append({
                "id":    page["id"],
                "title": page["title"],
                "body":  plain_text,
                "url":   f"{CONFLUENCE_BASE_URL}/wiki/spaces/{space_key}/pages/{page['id']}",
            })

        # Pagination
        next_start = data.get("_links", {}).get("next")
        if not next_start:
            break
        params["start"] += 25

    print(f"[ConfluenceAPI] Fetched {len(pages)} pages from space '{space_key}'")
    return pages


def get_page_by_title(title: str, space_key: str = CONFLUENCE_SPACE_KEY) -> dict | None:
    """Fetch a single page by exact title."""
    url = f"{CONFLUENCE_BASE_URL}/wiki/rest/api/content"
    params = {"spaceKey": space_key, "title": title, "expand": "body.storage", "type": "page"}
    resp = requests.get(url, headers=_headers, auth=_auth, params=params)
    if not resp.ok:
        return None
    results = resp.json().get("results", [])
    if not results:
        return None
    page = results[0]
    body_html = page.get("body", {}).get("storage", {}).get("value", "")
    return {
        "id":    page["id"],
        "title": page["title"],
        "body":  _strip_html(body_html),
        "url":   f"{CONFLUENCE_BASE_URL}/wiki/spaces/{space_key}/pages/{page['id']}",
    }


def get_folder_child_pages(folder_id: str, space_key: str = CONFLUENCE_SPACE_KEY, limit: int = 50) -> list[dict]:
    """Fetch child pages of a specific Confluence folder."""
    # The /child/page endpoint correctly filters by parent ID
    url = f"{CONFLUENCE_BASE_URL}/wiki/rest/api/content/{folder_id}/child/page"
    params = {
        "expand": "body.storage",
        "limit": 25,
        "start": 0,
    }

    pages = []
    while len(pages) < limit:
        resp = requests.get(url, headers=_headers, auth=_auth, params=params)
        if not resp.ok:
            print(f"[ConfluenceAPI] Error {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        for page in results:
            body_html = page.get("body", {}).get("storage", {}).get("value", "")
            plain_text = _strip_html(body_html)
            pages.append({
                "id":    page["id"],
                "title": page["title"],
                "body":  plain_text,
                "url":   f"{CONFLUENCE_BASE_URL}/wiki/spaces/{space_key}/pages/{page['id']}",
            })

        # Pagination
        next_start = data.get("_links", {}).get("next")
        if not next_start:
            break
        params["start"] += 25

    print(f"[ConfluenceAPI] Fetched {len(pages)} child pages for folder ID '{folder_id}'")
    return pages


if __name__ == "__main__":
    pages = get_all_pages()
    for p in pages:
        print(f"  [{p['id']}] {p['title']} — {len(p['body'])} chars")
