"""
push_runbooks_to_confluence.py
Reads the 5 local runbook markdown files and creates them as pages
in the Confluence Cloud MFS space.
"""
import os
import sys
import re
import glob
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

BASE_URL   = os.getenv("CONFLUENCE_BASE_URL", "").rstrip("/")
EMAIL      = os.getenv("CONFLUENCE_USER_EMAIL", "")
API_KEY    = os.getenv("CONFLUENCE_API_KEY", "")
SPACE_KEY  = os.getenv("CONFLUENCE_SPACE_KEY", "MFS")
RUNBOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "runbooks")

auth    = HTTPBasicAuth(EMAIL, API_KEY)
headers = {"Accept": "application/json", "Content-Type": "application/json"}


def markdown_to_storage(md: str) -> str:
    """
    Convert basic Markdown to Confluence Storage Format (XHTML-ish).
    Handles headings, bold, code blocks, lists, and plain paragraphs.
    """
    lines   = md.split("\n")
    out     = []
    in_code = False
    in_list = False

    for line in lines:
        # Code fences
        if line.startswith("```"):
            if not in_code:
                out.append('<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA[')
                in_code = True
            else:
                out.append("]]></ac:plain-text-body></ac:structured-macro>")
                in_code = False
            continue

        if in_code:
            out.append(line)
            continue

        # Close list if needed
        if in_list and not line.startswith("- ") and not line.startswith("* "):
            out.append("</ul>")
            in_list = False

        # Headings
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            level = min(len(m.group(1)), 4)
            out.append(f"<h{level}>{m.group(2)}</h{level}>")
            continue

        # Bullet lists
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            text = line[2:]
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
            out.append(f"<li>{text}</li>")
            continue

        # Blank line → paragraph break
        if not line.strip():
            out.append("<br/>")
            continue

        # Bold inline
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        # Inline code
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)

        out.append(f"<p>{line}</p>")

    if in_list:
        out.append("</ul>")

    return "\n".join(out)


def page_exists(title: str) -> str | None:
    """Returns page ID if it already exists, else None."""
    url = f"{BASE_URL}/wiki/rest/api/content"
    r = requests.get(url, auth=auth, headers={"Accept": "application/json"},
                     params={"spaceKey": SPACE_KEY, "title": title, "type": "page"})
    if r.ok:
        results = r.json().get("results", [])
        if results:
            return results[0]["id"]
    return None


def create_or_update_page(title: str, storage_body: str) -> dict:
    existing_id = page_exists(title)

    if existing_id:
        # Update existing page
        ver_url = f"{BASE_URL}/wiki/rest/api/content/{existing_id}"
        ver_resp = requests.get(ver_url, auth=auth, headers={"Accept": "application/json"})
        version = ver_resp.json().get("version", {}).get("number", 1) + 1

        payload = {
            "version": {"number": version},
            "title": title,
            "type": "page",
            "body": {
                "storage": {"value": storage_body, "representation": "storage"}
            }
        }
        r = requests.put(ver_url, auth=auth, headers=headers, json=payload)
        action = "Updated"
    else:
        # Create new page
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": SPACE_KEY},
            "body": {
                "storage": {"value": storage_body, "representation": "storage"}
            }
        }
        url = f"{BASE_URL}/wiki/rest/api/content"
        r = requests.post(url, auth=auth, headers=headers, json=payload)
        action = "Created"

    if r.ok:
        page_id = r.json().get("id", "?")
        print(f"  ✓ {action}: '{title}' (id={page_id})")
        return {"ok": True, "id": page_id, "action": action}
    else:
        print(f"  ✗ Failed '{title}': {r.status_code} — {r.text[:200]}")
        return {"ok": False}


def main():
    runbook_files = sorted(glob.glob(os.path.join(RUNBOOKS_DIR, "*.md")))
    if not runbook_files:
        print("No runbook files found in ./runbooks/")
        sys.exit(1)

    print(f"\nPushing {len(runbook_files)} runbooks → Confluence space '{SPACE_KEY}'")
    print(f"  Target: {BASE_URL}/wiki/spaces/{SPACE_KEY}/pages\n")

    success = 0
    for path in runbook_files:
        filename = os.path.basename(path)
        # Derive a human-friendly title from filename
        title = filename.replace(".md", "").replace("_", " ").title()
        # Prefix so they're easy to find
        title = f"SRE Runbook: {title}"

        with open(path, "r") as f:
            md_content = f.read()

        storage_body = markdown_to_storage(md_content)
        result = create_or_update_page(title, storage_body)
        if result["ok"]:
            success += 1

    print(f"\n  Done — {success}/{len(runbook_files)} pages pushed to Confluence.")
    print(f"  View at: {BASE_URL}/wiki/spaces/{SPACE_KEY}/pages\n")


if __name__ == "__main__":
    main()
