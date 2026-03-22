#!/usr/bin/env python3
"""Download all transcripts from a Vimeo folder as .txt files."""

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


def extract_folder_id(url: str) -> str:
    """Extract the folder ID from a Vimeo folder URL.

    Supports formats like:
      https://vimeo.com/manage/folders/12345678
      https://vimeo.com/showcase/12345678
    """
    match = re.search(r"/(?:folders?|showcase)/(\d+)", url)
    if not match:
        # Maybe they just passed a numeric ID directly
        if re.fullmatch(r"\d+", url.strip()):
            return url.strip()
        print(f"Error: could not extract a folder ID from '{url}'")
        print("Expected a URL like: https://vimeo.com/manage/folders/12345678")
        sys.exit(1)
    return match.group(1)


def paginate(path: str, params: dict | None = None) -> list[dict]:
    """Fetch all pages from a Vimeo API endpoint."""
    results = []
    page = 1
    per_page = 100
    base_params = dict(params or {})
    while True:
        data = api_get(path, {**base_params, "per_page": per_page, "page": page})
        if "data" not in data:
            print(f"Error fetching {path}: {data}")
            sys.exit(1)
        results.extend(data["data"])
        if data["paging"]["next"] is None:
            break
        page += 1
    return results


def get_folder_info(folder_id: str) -> dict:
    """Fetch metadata for a single folder."""
    return api_get(f"/me/projects/{folder_id}")


def get_videos_in_folder(folder_id: str) -> list[dict]:
    """Fetch all videos inside a Vimeo folder."""
    return paginate(f"/me/projects/{folder_id}/videos")


def download_transcript(video: dict, target_dir: str) -> bool:
    """Download the transcript for a single video into target_dir. Returns True if saved."""
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
    filepath = os.path.join(target_dir, filename)

    # Avoid overwriting — append a number if file exists
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(target_dir, f"{sanitize_filename(title)}_{counter}.txt")
        counter += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(plain_text)

    return True


def main():
    if not ACCESS_TOKEN:
        print("Error: VIMEO_ACCESS_TOKEN not set. Copy .env.example to .env and add your token.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python download_transcripts.py <vimeo-folder-url>")
        print("  e.g. python download_transcripts.py https://vimeo.com/manage/folders/12345678")
        sys.exit(1)

    folder_id = extract_folder_id(sys.argv[1])

    # Verify credentials
    me = api_get("/me")
    if "name" not in me:
        print(f"Authentication failed: {me}")
        sys.exit(1)
    print(f"Authenticated as: {me['name']}")

    # Get folder name from API
    folder_info = get_folder_info(folder_id)
    folder_name = sanitize_filename(folder_info.get("name", folder_id))
    print(f"Folder: {folder_name}")

    target_dir = os.path.join(TRANSCRIPTS_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    print("Fetching videos...")
    videos = get_videos_in_folder(folder_id)
    print(f"Found {len(videos)} video(s). Downloading transcripts...\n")

    downloaded = 0
    skipped = 0
    for i, video in enumerate(videos, 1):
        title = video.get("name", "untitled")
        sys.stdout.write(f"[{i}/{len(videos)}] {title[:60]}... ")
        sys.stdout.flush()
        if download_transcript(video, target_dir):
            print("OK")
            downloaded += 1
        else:
            print("no transcript")
            skipped += 1

    print(f"\nDone! {downloaded} transcripts saved to {target_dir}/")
    if skipped:
        print(f"({skipped} videos had no transcript)")


if __name__ == "__main__":
    main()
