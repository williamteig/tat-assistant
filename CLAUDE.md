# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

TAT Assistant is an automated pipeline that pulls content from Vimeo, Circle, Instagram, Facebook, YouTube, and TikTok — stores it in Supabase — then consolidates it into Markdown knowledge documents uploaded to a Claude project via the Anthropic Files API. GitHub Actions runs the full pipeline every 6 hours.

## Running the web interface

```bash
.venv/bin/streamlit run streamlit_app.py
```

Opens at http://localhost:8501 with two tabs:
- **Chat** — ask questions answered from Greg's content
- **Data** — browse all transcripts and posts in Supabase

## Running the pipeline

```bash
# Full pipeline (all 5 steps)
python run_sync.py

# Common variants
python run_sync.py --full              # ignore watermarks, re-fetch everything
python run_sync.py --skip-upload       # generate docs but don't upload to Claude
python run_sync.py --only vimeo circle # run specific steps only
```

### Individual steps

```bash
python tools/vimeo/fetch_transcripts.py --new-only
python tools/circle/fetch_posts.py --full
python tools/social/monitor.py --platform youtube
python tools/claude/generate_knowledge.py --days 90
python tools/claude/upload_knowledge.py --dry-run
```

## Architecture

### Data flow

```
External APIs → tools/*/  →  Supabase (PostgreSQL)  →  tools/claude/  →  Anthropic Files API
```

`run_sync.py` runs 5 steps in sequence: **vimeo → circle → social → generate → upload**. Each step is independent — a failure in one is logged but does not stop the others.

### Incremental sync (watermarking)

By default every tool runs incrementally. Each tool queries Supabase for the most recent `posted_at` timestamp and only fetches content newer than that. `--full` overrides this for all steps; individual tools also accept their own `--full` or `--new-only` flags.

All writes use `.upsert()` so re-running any step is safe.

### Knowledge documents

`tools/claude/generate_knowledge.py` reads Supabase and writes 4 Markdown files to `knowledge/`:

| File | Content |
|------|---------|
| `transcripts_core.md` | Website Videos, Blogs, Newsletter transcripts (all time) |
| `transcripts_livestreams.md` | Livestreams and Insta Lives (all time) |
| `community_circle.md` | Circle posts + comments (rolling window, default 90 days) |
| `social_feed.md` | Social posts + top comments (rolling window, default 90 days) |

`tools/claude/upload_knowledge.py` uploads these to the Anthropic Files API, deletes the previous version of each file, and records the new file IDs in `claude_sync_log`.

### Database (`data/`)

`data/db.py` is a singleton Supabase client — import `get_client()` from it wherever DB access is needed. The schema is in `data/schema.sql` — run it once in the Supabase SQL Editor to initialise a new project.

### Social platforms

Each platform in `tools/social/monitor.py` is independent. If the relevant credentials are absent from `.env`, the platform is skipped gracefully. The same applies to Circle.

## Environment

All credentials come from `.env` (copy `.env.example` to get started). Required vars: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`, `CLAUDE_PROJECT_ID`, `VIMEO_ACCESS_TOKEN`. All social/Circle vars are optional.

Use the **service role key** for Supabase, not the anon key.

## GitHub Actions

`.github/workflows/sync.yml` runs on a `cron: "0 */6 * * *"` schedule. It also supports manual dispatch with `full_refetch` and `skip_upload` inputs. After each run it commits any changes to `knowledge/` back to main with `[skip ci]` to avoid recursive triggers.

All env vars must be added as GitHub Secrets (repo Settings → Secrets → Actions) using the same names as in `.env.example`.

## Related docs

- [plan.md](plan.md) — Project plan, architecture diagram, setup checklist, roadmap
