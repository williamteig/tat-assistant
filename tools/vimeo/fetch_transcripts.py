#!/usr/bin/env python3
"""
tools/vimeo/fetch_transcripts.py
=================================
Polls the Vimeo API for all videos, downloads any new or updated transcripts,
and stores them in Supabase.

• Deduplicates by Vimeo video ID — already-stored transcripts are skipped.
• Detects the video's folder/album and uses it as the category.
• Marks stored rows as in_knowledge=FALSE so the knowledge generator knows
  to include them in the next Claude upload.

Usage:
    python tools/vimeo/fetch_transcripts.py              # fetch everything
    python tools/vimeo/fetch_transcripts.py --new-only   # skip videos already in DB
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

ACCESS_TOKEN  = os.getenv("VIMEO_ACCESS_TOKEN")
FOLDER_URL    = os.getenv("VIMEO_FOLDER_URL", "").strip()
API_BASE      = "https://api.vimeo.com"

# ─── Vimeo API helpers ────────────────────────────────────────────────────────

def api_get(path: str, params: dict | None = None) -> dict:
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip(". ")[:200] or "untitled"


def strip_vtt(text: str) -> str:
    """Convert VTT/SRT caption text to plain readable text."""
    lines = text.splitlines()
    seen, result = set(), []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"\d{2}:\d{2}", line) and "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line and line not in seen:
            seen.add(line)
            result.append(line)
    return "\n".join(result)


def get_folder_id(folder_url: str) -> str | None:
    """Extract the numeric folder ID from a Vimeo folder URL."""
    m = re.search(r"/folder/(\d+)", folder_url)
    return m.group(1) if m else None


def get_videos_from_folder(folder_id: str) -> list[dict]:
    """Fetch all videos directly inside a folder."""
    videos, page = [], 1
    while True:
        data = api_get(f"/me/projects/{folder_id}/videos",
                       {"per_page": 100, "page": page,
                        "fields": "uri,name,duration,link,parent_folder"})
        if "data" not in data:
            break
        videos.extend(data["data"])
        if not data["paging"].get("next"):
            break
        page += 1
    return videos


def get_subfolders(folder_id: str) -> list[dict]:
    """Return sub-folders of a given folder."""
    try:
        data = api_get(f"/me/projects/{folder_id}/items",
                       {"per_page": 100, "fields": "type,folder"})
        return [item["folder"] for item in data.get("data", [])
                if item.get("type") == "folder" and item.get("folder")]
    except Exception:
        return []


def get_all_videos() -> list[dict]:
    folder_id = get_folder_id(FOLDER_URL) if FOLDER_URL else None
    if not folder_id:
        # No folder set — fetch all videos on the account
        videos, page = [], 1
        while True:
            data = api_get("/me/videos", {"per_page": 100, "page": page,
                                          "fields": "uri,name,duration,link,parent_folder"})
            if "data" not in data:
                print(f"[vimeo] Error fetching videos: {data}")
                sys.exit(1)
            videos.extend(data["data"])
            print(f"  Page {page} — {len(videos)}/{data.get('total', '?')} videos")
            if not data["paging"].get("next"):
                break
            page += 1
        return videos

    # Folder set — fetch videos from the folder and all its sub-folders
    print(f"[vimeo] Restricting to folder ID {folder_id} (and sub-folders)")
    videos = get_videos_from_folder(folder_id)
    subfolders = get_subfolders(folder_id)
    if subfolders:
        print(f"[vimeo] Found {len(subfolders)} sub-folder(s) — fetching videos from each")
        for sf in subfolders:
            sf_id   = sf["uri"].rstrip("/").split("/")[-1]
            sf_name = sf.get("name", sf_id)
            sf_vids = get_videos_from_folder(sf_id)
            print(f"  {sf_name}: {len(sf_vids)} video(s)")
            videos.extend(sf_vids)
    print(f"[vimeo] Total: {len(videos)} videos across folder + sub-folders")
    return videos


def get_transcript(video: dict) -> str | None:
    """Fetch and clean the transcript for a video. Returns None if unavailable."""
    uri = video["uri"]
    try:
        data = api_get(f"{uri}/texttracks")
    except requests.HTTPError:
        return None
    tracks = data.get("data", [])
    if not tracks:
        return None
    track = tracks[0]
    for t in tracks:
        if t.get("type") in ("subtitles", "captions"):
            track = t
            break
    link = track.get("link")
    if not link:
        return None
    r = requests.get(link, timeout=30)
    r.raise_for_status()
    return strip_vtt(r.text) or None


def extract_video_id(uri: str) -> str:
    """Extract the numeric ID from a Vimeo URI like /videos/123456."""
    return uri.rstrip("/").split("/")[-1]


def get_category(video: dict) -> str:
    """Derive a category name from the video's parent folder."""
    folder = video.get("parent_folder")
    if folder and isinstance(folder, dict):
        return folder.get("name", "Uncategorised")
    return "Uncategorised"


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-only", action="store_true",
                        help="Skip videos that already exist in Supabase")
    args = parser.parse_args()

    if not ACCESS_TOKEN:
        print("Error: VIMEO_ACCESS_TOKEN not set in .env")
        sys.exit(1)

    # Late import so missing supabase-py doesn't break --help
    from data.db import get_client
    sb = get_client()

    # Fetch existing IDs if --new-only
    existing_ids: set[str] = set()
    if args.new_only:
        rows = sb.table("transcripts").select("id").execute()
        existing_ids = {r["id"] for r in (rows.data or [])}
        print(f"[vimeo] {len(existing_ids)} transcripts already in Supabase — skipping those")

    me = api_get("/me")
    print(f"[vimeo] Authenticated as: {me.get('name', '?')}")

    print("[vimeo] Fetching video list...")
    videos = get_all_videos()
    print(f"[vimeo] Found {len(videos)} videos\n")

    saved = skipped = no_transcript = 0

    for i, video in enumerate(videos, 1):
        vid_id   = extract_video_id(video["uri"])
        title    = video.get("name", "untitled")
        category = get_category(video)

        sys.stdout.write(f"[{i}/{len(videos)}] {title[:55]:<55} ")
        sys.stdout.flush()

        if args.new_only and vid_id in existing_ids:
            print("already stored — skip")
            skipped += 1
            continue

        transcript = get_transcript(video)
        if not transcript:
            print("no transcript")
            no_transcript += 1
            continue

        sb.table("transcripts").upsert({
            "id":           vid_id,
            "title":        title,
            "category":     category,
            "content":      transcript,
            "duration_secs": video.get("duration"),
            "vimeo_url":    video.get("link"),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "updated_at":   datetime.now(timezone.utc).isoformat(),
            "in_knowledge": False,   # mark for re-upload to Claude
        }).execute()

        print("saved ✓")
        saved += 1

    print(f"\n[vimeo] Done — {saved} saved, {skipped} skipped, {no_transcript} had no transcript")


if __name__ == "__main__":
    main()
