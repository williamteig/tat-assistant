#!/usr/bin/env python3
"""
tools/claude/upload_knowledge.py
==================================
Uploads the generated knowledge/ documents to the Anthropic Files API,
replaces any previously uploaded version, and logs the new file IDs in Supabase.

The Files API makes these documents available to reference in Claude conversations.
Once uploaded, copy the file IDs into your Claude Project's knowledge settings
(or use the Project API if/when Anthropic exposes it).

Usage:
    python tools/claude/upload_knowledge.py
    python tools/claude/upload_knowledge.py --dry-run   # show what would be uploaded
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

KNOWLEDGE_DIR   = Path(__file__).parents[2] / "knowledge"
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")

# The four documents we manage
KNOWLEDGE_FILES = [
    "transcripts_core.md",
    "transcripts_livestreams.md",
    "community_circle.md",
    "social_feed.md",
]


def get_previous_file_id(sb, filename: str) -> str | None:
    """Look up the Anthropic file ID from the last upload of this document."""
    result = sb.table("claude_sync_log") \
        .select("claude_file_id") \
        .eq("knowledge_file", filename) \
        .execute()
    if result.data:
        return result.data[0]["claude_file_id"]
    return None


def log_upload(sb, filename: str, file_id: str, row_count: int, file_size: int):
    sb.table("claude_sync_log").upsert({
        "knowledge_file":  filename,
        "claude_file_id":  file_id,
        "uploaded_at":     datetime.now(timezone.utc).isoformat(),
        "row_count":       row_count,
        "file_size_bytes": file_size,
    }).execute()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be uploaded without uploading")
    args = parser.parse_args()

    if not ANTHROPIC_KEY:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    if not KNOWLEDGE_DIR.exists():
        print(f"Error: knowledge/ directory not found at {KNOWLEDGE_DIR}")
        print("Run tools/claude/generate_knowledge.py first.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    from data.db import get_client
    sb = get_client()

    print(f"[upload] {'DRY RUN — ' if args.dry_run else ''}Uploading knowledge documents\n")

    uploaded_ids = {}

    for filename in KNOWLEDGE_FILES:
        fpath = KNOWLEDGE_DIR / filename
        if not fpath.exists():
            print(f"  ⚠ {filename} — not found, skipping (run generate_knowledge.py first)")
            continue

        file_size = fpath.stat().st_size
        size_kb   = file_size // 1024

        if args.dry_run:
            print(f"  ~ {filename}  ({size_kb} KB) — would upload")
            continue

        # Delete previous version if it exists
        prev_id = get_previous_file_id(sb, filename)
        if prev_id:
            try:
                client.beta.files.delete(prev_id)
                print(f"  🗑  Deleted old {filename} (id: {prev_id})")
            except Exception as e:
                print(f"  ⚠ Could not delete old {filename}: {e}")

        # Upload new version
        with open(fpath, "rb") as f:
            uploaded = client.beta.files.upload(
                file=(filename, f, "text/plain"),
            )

        file_id = uploaded.id
        uploaded_ids[filename] = file_id

        # Count items (rough: count "## " headers)
        content  = fpath.read_text(encoding="utf-8")
        row_count = content.count("\n## ")

        log_upload(sb, filename, file_id, row_count, file_size)
        print(f"  ✓ {filename}  ({size_kb} KB, ~{row_count} items) → file_id: {file_id}")

    if not args.dry_run and uploaded_ids:
        print("\n" + "─" * 60)
        print("Files uploaded to Anthropic. File IDs:")
        for name, fid in uploaded_ids.items():
            print(f"  {name}: {fid}")
        print("\nTo add to your Claude Project:")
        print("  1. Open claude.ai → your TAT Assistant project")
        print("  2. Project Settings → Knowledge → Add content")
        print("  3. Paste each file ID above, or upload the files from knowledge/")
        print("─" * 60)

    print("\n[upload] Complete")


if __name__ == "__main__":
    main()
