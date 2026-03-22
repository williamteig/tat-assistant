#!/usr/bin/env python3
"""
tools/social/monitor.py
========================
Fetches posts and comments from Instagram, Facebook, YouTube, and TikTok
and stores them in Supabase. Runs incrementally — each platform tracks
its own watermark (most recent post already stored).

Each platform is independent — if a key is missing it is skipped gracefully.

Usage:
    python tools/social/monitor.py                    # all platforms
    python tools/social/monitor.py --platform instagram
    python tools/social/monitor.py --platform youtube
    python tools/social/monitor.py --platform facebook
    python tools/social/monitor.py --platform tiktok
    python tools/social/monitor.py --full             # ignore watermarks
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Callable

import requests
from dotenv import load_dotenv

load_dotenv()

# ─── Credentials ──────────────────────────────────────────────────────────────

INSTAGRAM_ACCOUNT_ID   = os.getenv("INSTAGRAM_ACCOUNT_ID")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
FACEBOOK_PAGE_ID       = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_ACCESS_TOKEN  = os.getenv("FACEBOOK_ACCESS_TOKEN")
YOUTUBE_API_KEY        = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_CHANNEL_ID     = os.getenv("YOUTUBE_CHANNEL_ID")
TIKTOK_ACCESS_TOKEN    = os.getenv("TIKTOK_ACCESS_TOKEN")

GRAPH_BASE = "https://graph.facebook.com/v19.0"
YT_BASE    = "https://www.googleapis.com/youtube/v3"

now_iso = lambda: datetime.now(timezone.utc).isoformat()

# ─── Supabase helpers ─────────────────────────────────────────────────────────

def upsert_post(sb, platform: str, post_id: str, payload: dict):
    sb.table("social_posts").upsert({
        "id":        f"{platform}:{post_id}",
        "platform":  platform,
        "post_id":   post_id,
        "fetched_at": now_iso(),
        "updated_at": now_iso(),
        "in_knowledge": False,
        **payload,
    }).execute()


def upsert_comment(sb, platform: str, post_id: str, comment_id: str, payload: dict):
    sb.table("social_comments").upsert({
        "id":         f"{platform}:{comment_id}",
        "platform":   platform,
        "post_id":    post_id,
        "comment_id": comment_id,
        "fetched_at": now_iso(),
        **payload,
    }).execute()


def get_watermark(sb, platform: str) -> str | None:
    """Return the ISO timestamp of the most recent post for this platform."""
    result = sb.table("social_posts") \
        .select("posted_at") \
        .eq("platform", platform) \
        .order("posted_at", desc=True) \
        .limit(1) \
        .execute()
    if result.data:
        return result.data[0]["posted_at"]
    return None


# ─── Instagram ────────────────────────────────────────────────────────────────

def fetch_instagram(sb, full: bool = False) -> int:
    if not INSTAGRAM_ACCOUNT_ID or not INSTAGRAM_ACCESS_TOKEN:
        print("[instagram] Skipped — credentials missing")
        return 0

    watermark = None if full else get_watermark(sb, "instagram")
    if watermark:
        print(f"[instagram] Incremental — fetching after {watermark}")

    fields = "id,caption,media_type,permalink,like_count,comments_count,timestamp"
    url    = f"{GRAPH_BASE}/{INSTAGRAM_ACCOUNT_ID}/media"
    params = {"fields": fields, "limit": 50, "access_token": INSTAGRAM_ACCESS_TOKEN}

    saved = 0
    while url:
        data = requests.get(url, params=params, timeout=30).json()
        posts = data.get("data", [])

        stop = False
        for post in posts:
            ts = post.get("timestamp", "")
            if watermark and ts and ts <= watermark:
                stop = True
                break

            upsert_post(sb, "instagram", post["id"], {
                "caption":       post.get("caption", ""),
                "media_type":    post.get("media_type"),
                "permalink":     post.get("permalink"),
                "likes":         post.get("like_count", 0),
                "comments_count": post.get("comments_count", 0),
                "posted_at":     ts,
            })
            saved += 1

            # Fetch comments
            _fetch_ig_comments(sb, post["id"])

        if stop or not data.get("paging", {}).get("next"):
            break
        url    = data["paging"]["next"]
        params = {}   # URL already includes params

    print(f"[instagram] {saved} post(s) stored")
    return saved


def _fetch_ig_comments(sb, post_id: str):
    url    = f"{GRAPH_BASE}/{post_id}/comments"
    params = {"fields": "id,text,username,like_count,timestamp",
              "limit": 100, "access_token": INSTAGRAM_ACCESS_TOKEN}
    while url:
        data = requests.get(url, params=params, timeout=30).json()
        for c in data.get("data", []):
            upsert_comment(sb, "instagram", post_id, c["id"], {
                "author":    c.get("username"),
                "text":      c.get("text", ""),
                "likes":     c.get("like_count", 0),
                "posted_at": c.get("timestamp"),
            })
        next_url = data.get("paging", {}).get("next")
        url    = next_url if next_url else None
        params = {}


# ─── Facebook ─────────────────────────────────────────────────────────────────

def fetch_facebook(sb, full: bool = False) -> int:
    if not FACEBOOK_PAGE_ID or not FACEBOOK_ACCESS_TOKEN:
        print("[facebook] Skipped — credentials missing")
        return 0

    watermark = None if full else get_watermark(sb, "facebook")
    if watermark:
        print(f"[facebook] Incremental — fetching after {watermark}")

    fields = "id,message,story,permalink_url,created_time,reactions.summary(true),comments.summary(true)"
    url    = f"{GRAPH_BASE}/{FACEBOOK_PAGE_ID}/posts"
    params = {"fields": fields, "limit": 50, "access_token": FACEBOOK_ACCESS_TOKEN}

    saved = 0
    while url:
        data = requests.get(url, params=params, timeout=30).json()
        posts = data.get("data", [])

        stop = False
        for post in posts:
            ts = post.get("created_time", "")
            if watermark and ts and ts <= watermark:
                stop = True
                break

            caption = post.get("message") or post.get("story", "")
            reactions = post.get("reactions", {}).get("summary", {}).get("total_count", 0)
            comments_count = post.get("comments", {}).get("summary", {}).get("total_count", 0)

            upsert_post(sb, "facebook", post["id"], {
                "caption":        caption,
                "permalink":      post.get("permalink_url"),
                "likes":          reactions,
                "comments_count": comments_count,
                "posted_at":      ts,
            })
            saved += 1
            _fetch_fb_comments(sb, post["id"])

        if stop or not data.get("paging", {}).get("next"):
            break
        url    = data["paging"]["next"]
        params = {}

    print(f"[facebook] {saved} post(s) stored")
    return saved


def _fetch_fb_comments(sb, post_id: str):
    url    = f"{GRAPH_BASE}/{post_id}/comments"
    params = {"fields": "id,message,from,like_count,created_time",
              "limit": 100, "access_token": FACEBOOK_ACCESS_TOKEN}
    while url:
        data = requests.get(url, params=params, timeout=30).json()
        for c in data.get("data", []):
            upsert_comment(sb, "facebook", post_id, c["id"], {
                "author":    c.get("from", {}).get("name"),
                "text":      c.get("message", ""),
                "likes":     c.get("like_count", 0),
                "posted_at": c.get("created_time"),
            })
        next_url = data.get("paging", {}).get("next")
        url    = next_url if next_url else None
        params = {}


# ─── YouTube ──────────────────────────────────────────────────────────────────

def fetch_youtube(sb, full: bool = False) -> int:
    if not YOUTUBE_API_KEY or not YOUTUBE_CHANNEL_ID:
        print("[youtube] Skipped — credentials missing")
        return 0

    watermark = None if full else get_watermark(sb, "youtube")
    if watermark:
        print(f"[youtube] Incremental — fetching after {watermark}")

    # Get uploads playlist ID
    ch = requests.get(f"{YT_BASE}/channels", params={
        "part": "contentDetails", "id": YOUTUBE_CHANNEL_ID, "key": YOUTUBE_API_KEY
    }, timeout=30).json()
    playlist_id = (ch.get("items") or [{}])[0] \
        .get("contentDetails", {}) \
        .get("relatedPlaylists", {}) \
        .get("uploads")
    if not playlist_id:
        print("[youtube] Could not find uploads playlist — check YOUTUBE_CHANNEL_ID")
        return 0

    saved = 0
    page_token = None

    while True:
        params = {"part": "snippet", "playlistId": playlist_id,
                  "maxResults": 50, "key": YOUTUBE_API_KEY}
        if page_token:
            params["pageToken"] = page_token

        data = requests.get(f"{YT_BASE}/playlistItems", params=params, timeout=30).json()
        items = data.get("items", [])

        stop = False
        for item in items:
            snip   = item["snippet"]
            vid_id = snip.get("resourceId", {}).get("videoId")
            ts     = snip.get("publishedAt", "")

            if watermark and ts and ts <= watermark:
                stop = True
                break

            caption = snip.get("description", "")
            title   = snip.get("title", "")
            full_caption = f"{title}\n\n{caption}".strip()

            upsert_post(sb, "youtube", vid_id, {
                "caption":    full_caption,
                "permalink":  f"https://www.youtube.com/watch?v={vid_id}",
                "posted_at":  ts,
            })
            saved += 1
            _fetch_yt_comments(sb, vid_id)

        if stop or not data.get("nextPageToken"):
            break
        page_token = data["nextPageToken"]

    print(f"[youtube] {saved} video(s) stored")
    return saved


def _fetch_yt_comments(sb, video_id: str):
    try:
        data = requests.get(f"{YT_BASE}/commentThreads", params={
            "part": "snippet", "videoId": video_id,
            "maxResults": 100, "key": YOUTUBE_API_KEY,
        }, timeout=30).json()
    except Exception:
        return
    for item in data.get("items", []):
        top = item["snippet"]["topLevelComment"]["snippet"]
        upsert_comment(sb, "youtube", video_id, item["id"], {
            "author":    top.get("authorDisplayName"),
            "text":      top.get("textDisplay", ""),
            "likes":     top.get("likeCount", 0),
            "posted_at": top.get("publishedAt"),
        })


# ─── TikTok ───────────────────────────────────────────────────────────────────

def fetch_tiktok(sb, full: bool = False) -> int:
    if not TIKTOK_ACCESS_TOKEN:
        print("[tiktok] Skipped — credentials missing")
        return 0

    watermark = None if full else get_watermark(sb, "tiktok")

    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }

    # TikTok Research API — query own videos
    payload = {
        "query": {"and": [{"operation": "EQ", "field_name": "username",
                           "field_values": [COMMUNITY_SLUG if COMMUNITY_SLUG else "tat"]}]},
        "start_date": watermark[:10].replace("-", "") if watermark else "20230101",
        "end_date":   datetime.now(timezone.utc).strftime("%Y%m%d"),
        "max_count":  100,
        "fields":     "id,create_time,username,video_description,like_count,comment_count,share_count",
    }

    saved = 0
    try:
        resp = requests.post(
            "https://open.tiktokapis.com/v2/research/video/query/",
            headers=headers, json=payload, timeout=30,
        )
        data = resp.json().get("data", {}).get("videos", [])
        for v in data:
            vid_id = str(v.get("id"))
            ts     = datetime.fromtimestamp(v.get("create_time", 0), tz=timezone.utc).isoformat()
            upsert_post(sb, "tiktok", vid_id, {
                "caption":        v.get("video_description", ""),
                "likes":          v.get("like_count", 0),
                "comments_count": v.get("comment_count", 0),
                "posted_at":      ts,
            })
            saved += 1
    except Exception as e:
        print(f"[tiktok] Error: {e}")

    print(f"[tiktok] {saved} video(s) stored")
    return saved

COMMUNITY_SLUG = os.getenv("CIRCLE_COMMUNITY_SLUG", "")

# ─── Main ─────────────────────────────────────────────────────────────────────

PLATFORMS: dict[str, Callable] = {
    "instagram": fetch_instagram,
    "facebook":  fetch_facebook,
    "youtube":   fetch_youtube,
    "tiktok":    fetch_tiktok,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=list(PLATFORMS.keys()),
                        help="Fetch only this platform")
    parser.add_argument("--full", action="store_true",
                        help="Ignore watermarks and re-fetch everything")
    args = parser.parse_args()

    from data.db import get_client
    sb = get_client()

    targets = [args.platform] if args.platform else list(PLATFORMS.keys())

    total = 0
    for name in targets:
        print(f"\n── {name.upper()} ──────────────────────────────")
        try:
            total += PLATFORMS[name](sb, full=args.full)
        except Exception as e:
            print(f"[{name}] Error: {e}")

    print(f"\n[social] Complete — {total} post(s) total stored across {len(targets)} platform(s)")


if __name__ == "__main__":
    main()
