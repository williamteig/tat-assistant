#!/usr/bin/env python3
"""
2-way sync between local Markdown files and Notion pages.

Usage:
    python sync.py            # Auto-detect direction for each file
    python sync.py --push     # Force push all MD files → Notion
    python sync.py --pull     # Force pull all Notion pages → MD files
    python sync.py --status   # Show sync status without making changes
    python sync.py --file business/team.md  # Sync a single file only

How direction is determined (auto mode):
    - If last_synced is null → push MD to Notion (initial sync)
    - If MD mtime > last_synced → MD is ahead → push MD to Notion
    - If Notion last_edited_time > last_synced → Notion is ahead → pull to MD
    - If both changed since last_synced → conflict (prints warning, skips)
    - If neither changed → already synced, skip

Requires NOTION_API_KEY in .env
"""

import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"
SYNC_MAP_PATH = Path(__file__).parent / "sync_map.json"
PROJECT_ROOT = Path(__file__).parent

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

# ─── Notion API helpers ────────────────────────────────────────────────────────

def notion_get(path: str) -> dict:
    resp = requests.get(f"https://api.notion.com/v1{path}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def notion_patch(path: str, payload: dict) -> dict:
    resp = requests.patch(f"https://api.notion.com/v1{path}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def notion_post(path: str, payload: dict) -> dict:
    resp = requests.post(f"https://api.notion.com/v1{path}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def notion_delete(path: str) -> dict:
    resp = requests.delete(f"https://api.notion.com/v1{path}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def get_page_metadata(page_id: str) -> dict:
    return notion_get(f"/pages/{page_id}")


def get_all_blocks(block_id: str) -> list:
    """Fetch all blocks recursively (handles pagination)."""
    blocks = []
    cursor = None
    while True:
        params = f"?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        data = notion_get(f"/blocks/{block_id}/children{params}")
        for block in data.get("results", []):
            blocks.append(block)
            if block.get("has_children"):
                block["_children"] = get_all_blocks(block["id"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return blocks


def delete_all_blocks(page_id: str):
    """Delete all top-level blocks from a page."""
    data = notion_get(f"/blocks/{page_id}/children?page_size=100")
    for block in data.get("results", []):
        notion_delete(f"/blocks/{block['id']}")


def append_blocks(block_id: str, children: list):
    """Append blocks to a page or block in batches of 100."""
    for i in range(0, len(children), 100):
        batch = children[i:i + 100]
        notion_post(f"/blocks/{block_id}/children", {"children": batch})


# ─── Notion → Markdown ────────────────────────────────────────────────────────

def rich_text_to_md(rich_texts: list) -> str:
    """Convert Notion rich text array to Markdown inline text."""
    result = ""
    for rt in rich_texts:
        text = rt.get("plain_text", "")
        annotations = rt.get("annotations", {})
        href = rt.get("href")

        if annotations.get("code"):
            text = f"`{text}`"
        if annotations.get("bold"):
            text = f"**{text}**"
        if annotations.get("italic"):
            text = f"*{text}*"
        if annotations.get("strikethrough"):
            text = f"~~{text}~~"
        if href:
            text = f"[{text}]({href})"

        result += text
    return result


def blocks_to_md(blocks: list, indent: int = 0) -> str:
    """Convert a list of Notion blocks to Markdown text."""
    lines = []
    prefix = "  " * indent

    for block in blocks:
        btype = block["type"]
        b = block.get(btype, {})
        rt = b.get("rich_text", [])
        text = rich_text_to_md(rt)
        children_md = ""

        if block.get("_children"):
            children_md = "\n" + blocks_to_md(block["_children"], indent + 1)

        if btype == "heading_1":
            lines.append(f"{prefix}# {text}")
        elif btype == "heading_2":
            lines.append(f"{prefix}## {text}")
        elif btype == "heading_3":
            lines.append(f"{prefix}### {text}")
        elif btype == "paragraph":
            lines.append(f"{prefix}{text}" if text else "")
        elif btype == "bulleted_list_item":
            lines.append(f"{prefix}- {text}{children_md}")
        elif btype == "numbered_list_item":
            lines.append(f"{prefix}1. {text}{children_md}")
        elif btype == "to_do":
            checked = "x" if b.get("checked") else " "
            lines.append(f"{prefix}- [{checked}] {text}{children_md}")
        elif btype == "toggle":
            lines.append(f"{prefix}<details>\n{prefix}<summary>{text}</summary>\n{children_md}\n{prefix}</details>")
        elif btype == "code":
            lang = b.get("language", "")
            lines.append(f"{prefix}```{lang}\n{text}\n{prefix}```")
        elif btype == "quote":
            lines.append(f"{prefix}> {text}")
        elif btype == "callout":
            emoji = b.get("icon", {}).get("emoji", "")
            lines.append(f"{prefix}> {emoji} {text}")
        elif btype == "divider":
            lines.append(f"{prefix}---")
        elif btype == "table":
            if block.get("_children"):
                rows = block["_children"]
                table_lines = []
                for i, row in enumerate(rows):
                    cells = row.get("table_row", {}).get("cells", [])
                    row_text = "| " + " | ".join(rich_text_to_md(cell) for cell in cells) + " |"
                    table_lines.append(row_text)
                    if i == 0:
                        sep = "| " + " | ".join("---" for _ in cells) + " |"
                        table_lines.append(sep)
                lines.extend(table_lines)
        elif btype == "image":
            src = b.get("external", {}).get("url") or b.get("file", {}).get("url", "")
            caption = rich_text_to_md(b.get("caption", []))
            lines.append(f"{prefix}![{caption}]({src})")
        elif btype == "embed" or btype == "bookmark":
            url = b.get("url", "")
            lines.append(f"{prefix}[{url}]({url})")
        else:
            # Fallback: just include plain text if available
            if text:
                lines.append(f"{prefix}{text}")

    return "\n".join(lines)


# ─── Markdown → Notion blocks ─────────────────────────────────────────────────

def md_inline_to_rich_text(text: str) -> list:
    """Convert inline Markdown to Notion rich_text array (basic support)."""
    rich_texts = []
    # Pattern to match bold, italic, code, links
    pattern = re.compile(
        r'(\*\*(.+?)\*\*)'         # bold
        r'|(\*(.+?)\*)'            # italic
        r'|(`(.+?)`)'              # inline code
        r'|(\[(.+?)\]\((.+?)\))'   # link
        r'|(~~(.+?)~~)'            # strikethrough
    )

    last_end = 0
    for m in pattern.finditer(text):
        # Plain text before this match
        if m.start() > last_end:
            plain = text[last_end:m.start()]
            if plain:
                rich_texts.append({"type": "text", "text": {"content": plain}, "annotations": {}})

        if m.group(1):  # bold
            rich_texts.append({"type": "text", "text": {"content": m.group(2)}, "annotations": {"bold": True}})
        elif m.group(3):  # italic
            rich_texts.append({"type": "text", "text": {"content": m.group(4)}, "annotations": {"italic": True}})
        elif m.group(5):  # code
            rich_texts.append({"type": "text", "text": {"content": m.group(6)}, "annotations": {"code": True}})
        elif m.group(7):  # link
            rich_texts.append({"type": "text", "text": {"content": m.group(8), "link": {"url": m.group(9)}}, "annotations": {}})
        elif m.group(10):  # strikethrough
            rich_texts.append({"type": "text", "text": {"content": m.group(11)}, "annotations": {"strikethrough": True}})

        last_end = m.end()

    # Remaining plain text
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            rich_texts.append({"type": "text", "text": {"content": remaining}, "annotations": {}})

    if not rich_texts:
        rich_texts.append({"type": "text", "text": {"content": text}, "annotations": {}})

    return rich_texts


def md_to_blocks(md: str) -> list:
    """Convert Markdown text to a list of Notion block objects."""
    blocks = []
    lines = md.split("\n")
    i = 0

    # Strip the _Last synced_ line if present
    lines = [l for l in lines if not l.startswith("_Last synced:")]

    while i < len(lines):
        line = lines[i]

        # Blank line
        if not line.strip():
            i += 1
            continue

        # Headings
        if line.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": md_inline_to_rich_text(line[4:])}})
        elif line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": md_inline_to_rich_text(line[3:])}})
        elif line.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": md_inline_to_rich_text(line[2:])}})

        # Divider
        elif line.strip() == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        # Code block
        elif line.startswith("```"):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({"object": "block", "type": "code", "code": {
                "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                "language": lang or "plain text"
            }})

        # Blockquote
        elif line.startswith("> "):
            blocks.append({"object": "block", "type": "quote", "quote": {"rich_text": md_inline_to_rich_text(line[2:])}})

        # Checkbox / to-do
        elif re.match(r"^- \[[ x]\] ", line):
            checked = line[3] == "x"
            text = line[6:]
            blocks.append({"object": "block", "type": "to_do", "to_do": {
                "rich_text": md_inline_to_rich_text(text),
                "checked": checked
            }})

        # Bullet list
        elif line.startswith("- ") or line.startswith("* "):
            text = line[2:]
            blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {
                "rich_text": md_inline_to_rich_text(text)
            }})

        # Numbered list
        elif re.match(r"^\d+\. ", line):
            text = re.sub(r"^\d+\. ", "", line)
            blocks.append({"object": "block", "type": "numbered_list_item", "numbered_list_item": {
                "rich_text": md_inline_to_rich_text(text)
            }})

        # Table (look-ahead for | rows)
        elif line.startswith("|"):
            table_rows = []
            while i < len(lines) and lines[i].startswith("|"):
                row_line = lines[i].strip().strip("|")
                # Skip separator rows like |---|---|
                if re.match(r"^[\s\-|:]+$", row_line):
                    i += 1
                    continue
                cells = [cell.strip() for cell in row_line.split("|")]
                table_rows.append(cells)
                i += 1

            if table_rows:
                col_count = max(len(row) for row in table_rows)
                children = []
                for row in table_rows:
                    # Pad to col_count
                    while len(row) < col_count:
                        row.append("")
                    children.append({
                        "object": "block",
                        "type": "table_row",
                        "table_row": {
                            "cells": [md_inline_to_rich_text(cell) for cell in row]
                        }
                    })
                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": col_count,
                        "has_column_header": True,
                        "has_row_header": False,
                        "children": children
                    }
                })
            continue  # i already incremented in the while loop

        # Regular paragraph
        else:
            if line.strip():
                blocks.append({"object": "block", "type": "paragraph", "paragraph": {
                    "rich_text": md_inline_to_rich_text(line)
                }})

        i += 1

    return blocks


# ─── Sync operations ──────────────────────────────────────────────────────────

def pull_from_notion(file_path: str, page_id: str):
    """Pull Notion page content → local MD file."""
    print(f"  ← Pulling {file_path} from Notion...")
    blocks = get_all_blocks(page_id)
    md_content = blocks_to_md(blocks)

    full_path = PROJECT_ROOT / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(md_content + "\n")
    print(f"    ✓ Written to {file_path}")


def push_to_notion(file_path: str, page_id: str):
    """Push local MD file → Notion page content."""
    print(f"  → Pushing {file_path} to Notion...")
    full_path = PROJECT_ROOT / file_path
    if not full_path.exists():
        print(f"    ✗ File not found: {file_path}")
        return

    with open(full_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    blocks = md_to_blocks(md_content)

    # Clear existing content and replace
    delete_all_blocks(page_id)
    if blocks:
        append_blocks(page_id, blocks)

    print(f"    ✓ Pushed {len(blocks)} blocks to Notion")


def update_notion_sync_status(page_id: str, status: str, synced_at: str):
    """Update the Sync Status and Last Synced properties on the Notion row."""
    notion_patch(f"/pages/{page_id}", {
        "properties": {
            "Sync Status": {"select": {"name": status}},
            "Last Synced": {"date": {"start": synced_at}}
        }
    })


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_notion_time(t: str) -> datetime:
    """Parse Notion's ISO 8601 timestamp."""
    if not t:
        return datetime.min.replace(tzinfo=timezone.utc)
    t = t.replace("Z", "+00:00")
    return datetime.fromisoformat(t)


def parse_local_time(t: str | None) -> datetime:
    if not t:
        return datetime.min.replace(tzinfo=timezone.utc)
    t = t.replace("Z", "+00:00")
    return datetime.fromisoformat(t)


def get_md_mtime(file_path: str) -> datetime:
    full_path = PROJECT_ROOT / file_path
    if not full_path.exists():
        return datetime.min.replace(tzinfo=timezone.utc)
    mtime = os.path.getmtime(full_path)
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


# ─── Main sync logic ──────────────────────────────────────────────────────────

def load_sync_map() -> dict:
    with open(SYNC_MAP_PATH, "r") as f:
        return json.load(f)


def save_sync_map(sync_map: dict):
    with open(SYNC_MAP_PATH, "w") as f:
        json.dump(sync_map, f, indent=2)


def sync_file(file_path: str, entry: dict, force: str | None = None) -> str:
    """
    Sync a single file. force can be 'push', 'pull', or None (auto).
    Returns the result: 'pushed', 'pulled', 'skipped', 'conflict', 'error'
    """
    page_id = entry["notion_page_id"]
    last_synced_str = entry.get("last_synced")

    try:
        # Get Notion metadata
        meta = get_page_metadata(page_id)
        notion_edited = parse_notion_time(meta.get("last_edited_time"))
        last_synced = parse_local_time(last_synced_str)
        md_mtime = get_md_mtime(file_path)

        if force == "push":
            direction = "push"
        elif force == "pull":
            direction = "pull"
        else:
            # Auto-detect
            if last_synced_str is None:
                # Never synced — push MD as source of truth
                direction = "push"
            else:
                md_changed = md_mtime > last_synced
                notion_changed = notion_edited > last_synced

                if md_changed and notion_changed:
                    print(f"  ⚠ CONFLICT {file_path} — both MD and Notion changed since last sync. Skipping.")
                    update_notion_sync_status(page_id, "Conflict", now_iso())
                    return "conflict"
                elif md_changed:
                    direction = "push"
                elif notion_changed:
                    direction = "pull"
                else:
                    print(f"  ✓ Already in sync: {file_path}")
                    return "skipped"

        synced_at = now_iso()
        if direction == "push":
            push_to_notion(file_path, page_id)
            update_notion_sync_status(page_id, "Synced", synced_at)
        else:
            pull_from_notion(file_path, page_id)
            update_notion_sync_status(page_id, "Synced", synced_at)

        entry["last_synced"] = synced_at
        return direction

    except Exception as e:
        print(f"  ✗ Error syncing {file_path}: {e}")
        return "error"


def show_status(sync_map: dict):
    """Print sync status for each file without making changes."""
    print("\n📋 Sync Status\n" + "─" * 50)
    for file_path, entry in sync_map["files"].items():
        page_id = entry["notion_page_id"]
        last_synced_str = entry.get("last_synced")

        try:
            meta = get_page_metadata(page_id)
            notion_edited = parse_notion_time(meta.get("last_edited_time"))
            last_synced = parse_local_time(last_synced_str)
            md_mtime = get_md_mtime(file_path)

            if last_synced_str is None:
                status = "🆕 Never synced"
            else:
                md_changed = md_mtime > last_synced
                notion_changed = notion_edited > last_synced
                if md_changed and notion_changed:
                    status = "⚠️  Conflict (both changed)"
                elif md_changed:
                    status = "📝 MD ahead → needs push"
                elif notion_changed:
                    status = "☁️  Notion ahead → needs pull"
                else:
                    status = "✅ In sync"

            print(f"  {file_path:<40} {status}")
        except Exception as e:
            print(f"  {file_path:<40} ✗ Error: {e}")

    print()


def main():
    if not NOTION_API_KEY:
        print("✗ NOTION_API_KEY not set in .env")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="2-way sync between MD files and Notion")
    parser.add_argument("--push", action="store_true", help="Force push all MD files to Notion")
    parser.add_argument("--pull", action="store_true", help="Force pull all Notion pages to MD files")
    parser.add_argument("--status", action="store_true", help="Show sync status without making changes")
    parser.add_argument("--file", type=str, help="Sync a single file only (e.g. business/team.md)")
    args = parser.parse_args()

    sync_map = load_sync_map()

    if args.status:
        show_status(sync_map)
        return

    force = None
    if args.push:
        force = "push"
    elif args.pull:
        force = "pull"

    files = sync_map["files"]
    if args.file:
        if args.file not in files:
            print(f"✗ File not in sync_map: {args.file}")
            sys.exit(1)
        files = {args.file: files[args.file]}

    print(f"\n🔄 Syncing {len(files)} file(s)...\n")
    results = {"pushed": 0, "pulled": 0, "skipped": 0, "conflict": 0, "error": 0}

    for file_path, entry in files.items():
        result = sync_file(file_path, entry, force=force)
        results[result] = results.get(result, 0) + 1

    save_sync_map(sync_map)

    print(f"\n{'─'*50}")
    print(f"  ✅ Pushed:    {results['pushed']}")
    print(f"  ✅ Pulled:    {results['pulled']}")
    print(f"  ⏭  Skipped:   {results['skipped']}")
    print(f"  ⚠️  Conflicts: {results['conflict']}")
    print(f"  ✗  Errors:    {results['error']}")
    print()


if __name__ == "__main__":
    main()
