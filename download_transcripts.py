#!/usr/bin/env python3
"""Download all transcripts from a Vimeo account as .txt files."""

import os
import re
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

TRANSCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "transcripts")
ACCESS_TOKEN = os.getenv("VIMEO_ACCESS_TOKEN")
API_BASE = "https://api.vimeo.com"


def api_get(path: str, params: dict | None = None) -> dict:
    """Make an authenticated GET request to the Vimeo API."""
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def sanitize_filename(name: str) -> str:
    """Turn a video title into a safe filename."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip(". ")
    return name[:200] if name else "untitled"


def strip_vtt_formatting(text: str) -> str:
    """Convert VTT/SRT caption text to plain text, removing timestamps and tags."""
    lines = text.splitlines()
    seen = set()
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        if line.startswith("NOTE") or line.startswith("STYLE"):
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"\d{2}:\d{2}", line) and "-->" in line:
            continue
        # Strip HTML-like tags (e.g. <b>, <i>)
        line = re.sub(r"<[^>]+>", "", line)
        if line and line not in seen:
            seen.add(line)
            result.append(line)
    return "\n".join(result)


def get_all_videos() -> list[dict]:
    """Fetch all videos from the authenticated account, handling pagination."""
    videos = []
    page = 1
    per_page = 100
    while True:
        data = api_get("/me/videos", {"per_page": per_page, "page": page})
        if "data" not in data:
            print(f"Error fetching videos: {data}")
            sys.exit(1)
        videos.extend(data["data"])
        total = data.get("total", 0)
        print(f"  Fetched page {page} — {len(videos)}/{total} videos")
        if data["paging"]["next"] is None:
            break
        page += 1
    return videos


def download_transcript(video: dict) -> bool:
    """Download the transcript for a single video. Returns True if saved."""
    video_uri = video["uri"]  # e.g. /videos/123456
    title = video.get("name", "untitled")

    data = api_get(f"{video_uri}/texttracks")
    tracks = data.get("data", [])

    if not tracks:
        return False

    # Prefer 'subtitles' or 'captions' type; take the first available
    track = tracks[0]
    for t in tracks:
        if t.get("type") in ("subtitles", "captions"):
            track = t
            break

    link = track.get("link")
    if not link:
        return False

    text_resp = requests.get(link, timeout=30)
    text_resp.raise_for_status()

    plain_text = strip_vtt_formatting(text_resp.text)
    if not plain_text.strip():
        return False

    filename = sanitize_filename(title) + ".txt"
    filepath = os.path.join(TRANSCRIPTS_DIR, filename)

    # Avoid overwriting — append a number if file exists
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(TRANSCRIPTS_DIR, f"{sanitize_filename(title)}_{counter}.txt")
        counter += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(plain_text)

    return True


def main():
    if not ACCESS_TOKEN:
        print("Error: VIMEO_ACCESS_TOKEN not set. Copy .env.example to .env and add your token.")
        sys.exit(1)

    # Verify credentials
    me = api_get("/me")
    if "name" not in me:
        print(f"Authentication failed: {me}")
        sys.exit(1)
    print(f"Authenticated as: {me['name']}")

    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

    print("\nFetching video list...")
    videos = get_all_videos()
    print(f"\nFound {len(videos)} videos. Downloading transcripts...\n")

    downloaded = 0
    skipped = 0
    for i, video in enumerate(videos, 1):
        title = video.get("name", "untitled")
        sys.stdout.write(f"[{i}/{len(videos)}] {title[:60]}... ")
        sys.stdout.flush()
        if download_transcript(video):
            print("OK")
            downloaded += 1
        else:
            print("no transcript")
            skipped += 1

    print(f"\nDone! {downloaded} transcripts saved to {TRANSCRIPTS_DIR}/")
    if skipped:
        print(f"({skipped} videos had no transcript)")


if __name__ == "__main__":
    main()
