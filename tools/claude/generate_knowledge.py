#!/usr/bin/env python3
"""
tools/claude/generate_knowledge.py
====================================
Reads all content from Supabase and produces a small set of clean, consolidated
Markdown documents in the knowledge/ folder. These documents are what gets
uploaded to the Claude project — Claude reads them as its knowledge base.

Output files:
    knowledge/transcripts_core.md        — Website Videos, Blogs, Newsletter vids
    knowledge/transcripts_livestreams.md — Livestreams & Insta Lives
    knowledge/community_circle.md        — Circle posts (last 90 days by default)
    knowledge/social_feed.md             — Social posts + comments (last 90 days)

Usage:
    python tools/claude/generate_knowledge.py
    python tools/claude/generate_knowledge.py --days 180   # extend window
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

KNOWLEDGE_DIR = Path(__file__).parents[2] / "knowledge"
KNOWLEDGE_DIR.mkdir(exist_ok=True)

CORE_CATEGORIES = {
    "Website Videos", "Website Blogs", "Newsletter Videos",
    "Website", "Blog", "Newsletter",  # common aliases
}
LIVE_CATEGORIES = {
    "Livestreams", "Insta Lives", "Instagram Lives", "Live",
}


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "unknown date"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")
    except Exception:
        return iso[:10]


# ─── Transcript documents ─────────────────────────────────────────────────────

def generate_transcripts(sb, categories: set[str], output_file: Path, label: str):
    result = sb.table("transcripts") \
        .select("id,title,category,content,vimeo_url,fetched_at") \
        .order("fetched_at", desc=False) \
        .execute()

    rows = [r for r in (result.data or [])
            if r["category"] in categories or
               any(c.lower() in r["category"].lower() for c in categories)]

    if not rows:
        # Fall back: include everything not in the other category set
        all_rows = result.data or []
        other = LIVE_CATEGORIES if categories == CORE_CATEGORIES else CORE_CATEGORIES
        rows = [r for r in all_rows if r["category"] not in other]

    lines = [
        f"# Greg Apps — {label}",
        f"*Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')} "
        f"— {len(rows)} transcript(s)*",
        "",
        "---",
        "",
    ]

    for r in rows:
        lines += [
            f"## {r['title']}",
            f"**Category:** {r['category']}  |  "
            f"**Fetched:** {fmt_date(r.get('fetched_at'))}",
        ]
        if r.get("vimeo_url"):
            lines.append(f"**Source:** {r['vimeo_url']}")
        lines += ["", r["content"].strip(), "", "---", ""]

    output_file.write_text("\n".join(lines), encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(f"  ✓ {output_file.name}  ({len(rows)} transcripts, {size_kb} KB)")
    return len(rows)


# ─── Circle document ──────────────────────────────────────────────────────────

def generate_circle(sb, days: int, output_file: Path):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    posts = sb.table("circle_posts") \
        .select("id,space_name,author_name,title,body,post_url,posted_at") \
        .gte("posted_at", cutoff) \
        .order("posted_at", desc=False) \
        .execute().data or []

    # Fetch comments for each post in one go
    post_ids = [p["id"] for p in posts]
    all_comments = []
    if post_ids:
        all_comments = sb.table("circle_comments") \
            .select("post_id,author_name,body,posted_at") \
            .in_("post_id", post_ids) \
            .order("posted_at", desc=False) \
            .execute().data or []

    comments_by_post: dict[str, list] = {}
    for c in all_comments:
        comments_by_post.setdefault(c["post_id"], []).append(c)

    lines = [
        "# TAT Community — Circle Posts",
        f"*Last {days} days — {len(posts)} post(s) — "
        f"generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}*",
        "",
        "---",
        "",
    ]

    for p in posts:
        space = p.get("space_name") or "General"
        title = p.get("title") or "(no title)"
        author = p.get("author_name") or "Member"
        date = fmt_date(p.get("posted_at"))

        lines += [
            f"## {title}",
            f"**Space:** {space}  |  **By:** {author}  |  **Date:** {date}",
        ]
        if p.get("post_url"):
            lines.append(f"**Link:** {p['post_url']}")
        lines += ["", p["body"].strip(), ""]

        post_comments = comments_by_post.get(p["id"], [])
        if post_comments:
            lines.append(f"**{len(post_comments)} comment(s):**")
            for c in post_comments:
                c_author = c.get("author_name") or "Member"
                c_date   = fmt_date(c.get("posted_at"))
                c_body   = c["body"].strip().replace("\n", " ")
                lines.append(f"- **{c_author}** ({c_date}): {c_body}")
        lines += ["", "---", ""]

    output_file.write_text("\n".join(lines), encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(f"  ✓ {output_file.name}  ({len(posts)} posts, {size_kb} KB)")
    return len(posts)


# ─── Social feed document ─────────────────────────────────────────────────────

def generate_social(sb, days: int, output_file: Path):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    posts = sb.table("social_posts") \
        .select("id,platform,post_id,caption,permalink,likes,comments_count,posted_at") \
        .gte("posted_at", cutoff) \
        .order("posted_at", desc=False) \
        .execute().data or []

    post_ids = [p["post_id"] for p in posts]
    all_comments = []
    if post_ids:
        all_comments = sb.table("social_comments") \
            .select("post_id,platform,author,text,likes,posted_at") \
            .in_("post_id", post_ids) \
            .order("posted_at", desc=False) \
            .execute().data or []

    comments_by_post: dict[str, list] = {}
    for c in all_comments:
        comments_by_post.setdefault(c["post_id"], []).append(c)

    platform_emoji = {
        "instagram": "📸", "facebook": "👥",
        "youtube": "▶️", "tiktok": "🎵",
    }

    lines = [
        "# TAT Social Media — Posts & Comments",
        f"*Last {days} days — {len(posts)} post(s) — "
        f"generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}*",
        "",
        "---",
        "",
    ]

    for p in posts:
        emoji    = platform_emoji.get(p["platform"], "📱")
        platform = p["platform"].capitalize()
        date     = fmt_date(p.get("posted_at"))
        caption  = (p.get("caption") or "").strip()[:800]  # cap length

        lines += [
            f"## {emoji} {platform} — {date}",
            f"**Likes:** {p.get('likes', 0)}  |  "
            f"**Comments:** {p.get('comments_count', 0)}",
        ]
        if p.get("permalink"):
            lines.append(f"**Link:** {p['permalink']}")
        lines += ["", caption, ""]

        post_comments = comments_by_post.get(p["post_id"], [])
        if post_comments:
            lines.append(f"**Top comments ({len(post_comments)}):**")
            # Show top 10 by likes
            top = sorted(post_comments, key=lambda c: c.get("likes", 0), reverse=True)[:10]
            for c in top:
                c_author = c.get("author") or "User"
                c_text   = (c.get("text") or "").strip().replace("\n", " ")[:300]
                c_likes  = c.get("likes", 0)
                lines.append(f"- **{c_author}** (👍 {c_likes}): {c_text}")
        lines += ["", "---", ""]

    output_file.write_text("\n".join(lines), encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(f"  ✓ {output_file.name}  ({len(posts)} posts, {size_kb} KB)")
    return len(posts)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90,
                        help="How many days back to include for Circle & social (default 90)")
    args = parser.parse_args()

    from data.db import get_client
    sb = get_client()

    print(f"[knowledge] Generating documents into {KNOWLEDGE_DIR}/\n")

    counts = {}

    counts["transcripts_core"] = generate_transcripts(
        sb, CORE_CATEGORIES,
        KNOWLEDGE_DIR / "transcripts_core.md",
        "Core Teachings (Website, Blog & Newsletter Videos)",
    )

    counts["transcripts_livestreams"] = generate_transcripts(
        sb, LIVE_CATEGORIES,
        KNOWLEDGE_DIR / "transcripts_livestreams.md",
        "Livestreams & Instagram Lives",
    )

    counts["community_circle"] = generate_circle(
        sb, args.days,
        KNOWLEDGE_DIR / "community_circle.md",
    )

    counts["social_feed"] = generate_social(
        sb, args.days,
        KNOWLEDGE_DIR / "social_feed.md",
    )

    print(f"\n[knowledge] Done — {sum(counts.values())} total items across 4 documents")
    return counts


if __name__ == "__main__":
    main()
