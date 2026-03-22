#!/usr/bin/env python3
"""
tools/circle/fetch_posts.py
============================
Polls the Circle community API for new posts and comments, storing them
in Supabase. Runs incrementally — only fetches posts newer than the most
recent post already in the database.

Circle API docs: https://api.circle.so

Requirements in .env:
    CIRCLE_API_TOKEN       — API token from Settings → API in Circle
    CIRCLE_COMMUNITY_SLUG  — your subdomain (e.g. "theauditiontechnique")
    CIRCLE_SPACE_IDS       — optional comma-separated list of space IDs to watch

Usage:
    python tools/circle/fetch_posts.py            # incremental (new posts only)
    python tools/circle/fetch_posts.py --full     # full re-fetch of all posts
"""

import argparse
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

API_TOKEN      = os.getenv("CIRCLE_API_TOKEN")
COMMUNITY_SLUG = os.getenv("CIRCLE_COMMUNITY_SLUG")
SPACE_IDS_RAW  = os.getenv("CIRCLE_SPACE_IDS", "")
SPACE_IDS      = [s.strip() for s in SPACE_IDS_RAW.split(",") if s.strip()]

API_BASE = "https://app.circle.so/api/v1"

# ─── API helpers ──────────────────────────────────────────────────────────────

def headers() -> dict:
    return {
        "Authorization": f"Token {API_TOKEN}",
        "Content-Type":  "application/json",
    }


def api_get(path: str, params: dict | None = None) -> dict | list:
    resp = requests.get(
        f"{API_BASE}{path}",
        headers=headers(),
        params=params,
        timeout=30,
    )
    if resp.status_code == 401:
        print("[circle] 401 Unauthorised — check your CIRCLE_API_TOKEN")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


def get_spaces() -> list[dict]:
    """Return all spaces in the community (or only the ones configured)."""
    data = api_get("/spaces", {"community_slug": COMMUNITY_SLUG, "per_page": 100})
    spaces = data if isinstance(data, list) else data.get("spaces", [])
    if SPACE_IDS:
        spaces = [s for s in spaces if str(s.get("id")) in SPACE_IDS]
    return spaces


def get_posts_for_space(space_id: int, after_date: str | None = None) -> list[dict]:
    """Fetch all posts in a space, optionally filtered to after a date."""
    posts, page = [], 1
    while True:
        params = {
            "community_slug": COMMUNITY_SLUG,
            "space_id":       space_id,
            "per_page":       50,
            "page":           page,
            "sort":           "published_at_desc",
        }
        data = api_get("/posts", params)
        items = data if isinstance(data, list) else data.get("posts", [])
        if not items:
            break

        for post in items:
            published = post.get("published_at") or post.get("created_at", "")
            # Stop paginating if we've reached posts older than our watermark
            if after_date and published and published < after_date:
                return posts
            posts.append(post)

        # Circle paginates with has_next_page or by checking if page returned full set
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        if not meta.get("has_next_page", False) and len(items) < 50:
            break
        page += 1

    return posts


def get_comments_for_post(post_id: int) -> list[dict]:
    """Fetch all comments for a post."""
    try:
        data = api_get(f"/posts/{post_id}/comments", {
            "community_slug": COMMUNITY_SLUG,
            "per_page": 100,
        })
        return data if isinstance(data, list) else data.get("comments", [])
    except requests.HTTPError:
        return []


# ─── Storage helpers ──────────────────────────────────────────────────────────

def upsert_post(sb, post: dict, space_name: str):
    post_id = str(post.get("id") or post.get("slug"))
    body = post.get("body_plain_text") or post.get("body") or ""
    # Strip basic HTML if body_plain_text isn't available
    if "<" in body:
        import re
        body = re.sub(r"<[^>]+>", " ", body).strip()

    sb.table("circle_posts").upsert({
        "id":             post_id,
        "space_name":     space_name,
        "author_name":    post.get("user_name") or post.get("author", {}).get("name"),
        "author_email":   post.get("user_email"),
        "title":          post.get("name") or post.get("title"),
        "body":           body,
        "post_url":       post.get("url"),
        "likes":          post.get("likes_count", 0),
        "comments_count": post.get("comments_count", 0),
        "posted_at":      post.get("published_at") or post.get("created_at"),
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "updated_at":     datetime.now(timezone.utc).isoformat(),
        "in_knowledge":   False,
    }).execute()
    return post_id


def upsert_comment(sb, comment: dict, post_id: str):
    comment_id = str(comment.get("id"))
    body = comment.get("body_plain_text") or comment.get("body") or ""
    if "<" in body:
        import re
        body = re.sub(r"<[^>]+>", " ", body).strip()

    sb.table("circle_comments").upsert({
        "id":          comment_id,
        "post_id":     post_id,
        "author_name": comment.get("user_name") or comment.get("author", {}).get("name"),
        "body":        body,
        "likes":       comment.get("likes_count", 0),
        "posted_at":   comment.get("created_at"),
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
    }).execute()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true",
                        help="Re-fetch all posts, not just new ones")
    args = parser.parse_args()

    if not API_TOKEN or not COMMUNITY_SLUG:
        print("Error: CIRCLE_API_TOKEN and CIRCLE_COMMUNITY_SLUG must be set in .env")
        sys.exit(1)

    from data.db import get_client
    sb = get_client()

    # Find watermark — most recent post already stored
    after_date: str | None = None
    if not args.full:
        result = sb.table("circle_posts") \
            .select("posted_at") \
            .order("posted_at", desc=True) \
            .limit(1) \
            .execute()
        if result.data:
            after_date = result.data[0]["posted_at"]
            print(f"[circle] Incremental mode — fetching posts after {after_date}")
        else:
            print("[circle] No existing posts — doing full fetch")

    print("[circle] Fetching spaces...")
    spaces = get_spaces()
    if not spaces:
        print("[circle] No spaces found. Check CIRCLE_COMMUNITY_SLUG and CIRCLE_SPACE_IDS.")
        sys.exit(1)
    print(f"[circle] Found {len(spaces)} space(s): {[s.get('name') for s in spaces]}\n")

    total_posts = total_comments = 0

    for space in spaces:
        space_id   = space["id"]
        space_name = space.get("name", f"Space {space_id}")
        print(f"[circle] → Space: {space_name}")

        posts = get_posts_for_space(space_id, after_date if not args.full else None)
        print(f"          {len(posts)} new post(s)")

        for post in posts:
            post_id = upsert_post(sb, post, space_name)
            total_posts += 1

            # Fetch comments for this post
            comments = get_comments_for_post(post.get("id"))
            for comment in comments:
                upsert_comment(sb, comment, post_id)
            total_comments += len(comments)

            title = (post.get("name") or post.get("title") or "untitled")[:50]
            print(f"          • [{post_id}] {title} ({len(comments)} comment(s))")

    print(f"\n[circle] Done — {total_posts} posts, {total_comments} comments stored")


if __name__ == "__main__":
    main()
