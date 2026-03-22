# CHANGELOG — tat-assistant

All notable changes to this project are documented here.
This file is intended to give full context when resuming work in Claude CLI or any new session.

---

## [0.2.0] — 2026-03-22 (Cowork session)

### Project Renamed
- GitHub repo renamed from `vimeoscriptdownloader` to `tat-assistant` (done via GitHub web UI due to VM proxy block on git push)
- Local Mac folder renamed: `~/Documents/AppDev/vimeoscriptdownloader` to `~/Documents/AppDev/tat-assistant`
- Inner `vimeoscriptdownloader/` subfolder (legacy) deleted — its only file (`business/questionnaire.md`) already existed at root level
- Old legacy files `sync.py` and `sync_map.json` deleted (replaced by `run_sync.py`)

### Architecture Decision — Cloud Storage
- **Rejected**: SQLite (local-only, not accessible across machines)
- **Chosen**: Supabase (PostgreSQL in the cloud, free tier, accessible anywhere)
- **Why**: The sync pipeline runs on GitHub Actions (no local machine required), and Supabase gives a proper relational DB with no storage concerns for text data

### New Database Schema (`data/schema.sql`)
Created Supabase PostgreSQL schema with the following tables:
- `transcripts` — Vimeo video transcripts with category detection
- `social_posts` — Instagram, Facebook, YouTube, TikTok posts
- `social_comments` — Comments on social posts
- `circle_posts` — Circle community posts
- `circle_comments` — Comments on Circle posts
- `claude_sync_log` — Tracks Anthropic Files API file IDs per knowledge doc

Each content table has an `in_knowledge BOOLEAN DEFAULT FALSE` flag to track what has been included in the latest Claude knowledge upload.

### New Files Created

#### Core Infrastructure
- `data/schema.sql` — Full Supabase PostgreSQL schema (run this in Supabase SQL Editor)
- `data/__init__.py` — Package init
- `data/db.py` — Singleton Supabase client using `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` env vars
- `requirements.txt` — python-dotenv, requests, supabase>=2.4.0, anthropic>=0.25.0
- `.env.example` — Template for all required environment variables
- `.gitignore` — Standard Python + secrets ignore rules
- `README.md` — Project overview and setup instructions

#### Orchestrator
- `run_sync.py` (149 lines) — Master runner: vimeo -> circle -> social -> generate -> upload
  - Flags: `--full` (ignore watermarks), `--skip-upload`, `--only [steps]`
  - Prints a summary table of step results

#### Tool: Vimeo (`tools/vimeo/`)
- `fetch_transcripts.py` (193 lines) — Replaces old `download_transcripts.py`
  - Polls Vimeo API for videos
  - Detects category from `parent_folder.name` (Website Videos, Blogs, Newsletter, Livestreams, Insta Lives)
  - Strips VTT formatting from captions
  - Upserts to Supabase `transcripts` table
  - `--new-only` flag for incremental runs
- `__init__.py`

#### Tool: Circle (`tools/circle/`)
- `fetch_posts.py` (225 lines) — NEW — Circle community API integration
  - Incremental via watermark on `posted_at`
  - Fetches all spaces (or configured CIRCLE_SPACE_IDS)
  - Upserts posts and comments to Supabase
  - Strips basic HTML from post bodies
  - `--full` flag to re-fetch everything
- `__init__.py`

#### Tool: Social (`tools/social/`)
- `monitor.py` (386 lines) — NEW — Social media monitor
  - Platforms: Instagram, Facebook, YouTube, TikTok
  - Each platform skipped gracefully if credentials are missing
  - Incremental via `get_watermark()` per platform (most recent `posted_at` in DB)
  - Fetches posts + comments for each platform
  - `--full` flag to ignore watermarks
  - `--platform` flag to run a single platform
- `__init__.py`

#### Tool: Claude Knowledge (`tools/claude/`)
- `generate_knowledge.py` (272 lines) — Reads Supabase, generates 4 consolidated `.md` files:
  - `knowledge/transcripts_core.md` — Website Videos, Blogs, Newsletter transcripts
  - `knowledge/transcripts_livestreams.md` — Livestreams & Insta Lives
  - `knowledge/community_circle.md` — Circle posts + comments (last 90 days)
  - `knowledge/social_feed.md` — Social posts + top comments (last 90 days)
  - `--days N` argument to control rolling window
- `upload_knowledge.py` (138 lines) — Uploads knowledge docs to Anthropic Files API
  - Uses `anthropic.beta.files.upload()` to push `.md` files to Claude project
  - Deletes old file version before uploading new one (tracks IDs in `claude_sync_log`)
  - `--dry-run` flag for testing
- `__init__.py`

#### GitHub Actions
- `.github/workflows/sync.yml` — Automated sync workflow
  - Schedule: every 6 hours (`cron: "0 */6 * * *"`)
  - `workflow_dispatch` inputs: `full_refetch`, `skip_upload`
  - All API keys passed as GitHub Secrets
  - After sync, commits updated `knowledge/` docs with `[skip ci]`

#### Other
- `knowledge/.gitkeep` — Placeholder so `knowledge/` directory is tracked by git
- `tools/__init__.py`

### Existing Files Preserved
- `tools/vimeo/download_transcripts.py` — Original downloader kept for reference
- `tools/vimeo/transcripts/` — 52 existing transcript `.txt` files kept intact
  - Categories: Insta Lives, Livestreams, Newsletter Videos, Website Blogs, Website Videos
  - These can be imported into Supabase on first run with `--full`
- `business/` — All business planning docs kept as-is

---

## [0.1.0] — pre-2026-03-22 (original project)

### Initial State
- Project was named `vimeoscriptdownloader`
- Single tool: Vimeo transcript downloader (`tools/vimeo/download_transcripts.py`)
- Local SQLite storage
- 52 transcript files downloaded to `tools/vimeo/transcripts/`
- Business planning docs in `business/`

---

## Pending / Next Steps

### Immediate (required before first run)

1. **Git commit and push** — changes are on disk but not yet committed:
   ```bash
   cd ~/Documents/AppDev/tat-assistant
   git add -A
   git commit -m "feat: add full TAT sync pipeline (Supabase + Circle + Social + Claude)"
   git push origin main
   ```

2. **Set up Supabase**
   - Create free project at https://supabase.com
   - Go to SQL Editor, paste and run `data/schema.sql`
   - Copy Project URL and service_role key into `.env`

3. **Fill in `.env`**
   - Copy `.env.example` to `.env`
   - Add Supabase URL + service_role key
   - Add Anthropic API key + Claude Project ID
   - Add Vimeo access token
   - Add Circle API token + community slug
   - Add social platform credentials (Instagram, Facebook, YouTube, TikTok) — optional, each skipped gracefully if missing

4. **Add GitHub Secrets**
   - In repo Settings -> Secrets -> Actions
   - Add all vars from `.env.example` as secrets
   - The sync workflow will then run automatically every 6 hours

5. **First test run (no Claude upload)**
   ```bash
   cd ~/Documents/AppDev/tat-assistant
   python run_sync.py --full --skip-upload
   ```
   This runs vimeo + circle + social fetch and generates knowledge docs but does NOT upload to Claude.
   Check `knowledge/` to see the generated `.md` files.

6. **First full run with Claude upload**
   ```bash
   python run_sync.py --full
   ```

### Future Enhancements
- Import existing 52 transcript `.txt` files into Supabase (one-off migration script needed)
- TikTok Research API credentials setup (requires separate TikTok developer application)
- Webhook support for real-time Circle post ingestion
- Analytics dashboard showing content currently in the knowledge base

---

## Technical Notes for Claude CLI

### Directory
All project files are at: `~/Documents/AppDev/tat-assistant/`

### Project Structure
```
tat-assistant/
  business/             # Business planning docs (brand, curriculum, revenue, etc.)
  data/
    __init__.py
    db.py               # Supabase client singleton
    schema.sql          # PostgreSQL schema — run once in Supabase SQL Editor
  knowledge/            # Generated .md knowledge docs (auto-created on sync)
    .gitkeep
  tools/
    __init__.py
    circle/
      __init__.py
      fetch_posts.py    # Circle community API fetcher
    claude/
      __init__.py
      generate_knowledge.py  # Reads DB, writes .md knowledge files
      upload_knowledge.py    # Uploads .md files to Anthropic Files API
    social/
      __init__.py
      monitor.py        # Instagram, Facebook, YouTube, TikTok fetcher
    vimeo/
      __init__.py
      download_transcripts.py  # Original (kept for reference)
      fetch_transcripts.py     # New Supabase-backed version
      transcripts/             # 52 existing .txt transcript files
  .env                  # NOT committed — create from .env.example
  .env.example          # Credential template
  .gitignore
  .github/
    workflows/
      sync.yml          # GitHub Actions workflow (runs every 6 hours)
  CHANGELOG.md          # This file
  README.md
  requirements.txt
  run_sync.py           # Master orchestrator
```

### Key Environment Variables
```
SUPABASE_URL            # https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY    # service_role key (not anon key)
ANTHROPIC_API_KEY       # sk-ant-...
CLAUDE_PROJECT_ID       # From claude.ai/project/XXXX URL
VIMEO_ACCESS_TOKEN
CIRCLE_API_TOKEN
CIRCLE_COMMUNITY_SLUG
CIRCLE_SPACE_IDS        # Optional comma-separated IDs
INSTAGRAM_ACCOUNT_ID
INSTAGRAM_ACCESS_TOKEN
FACEBOOK_PAGE_ID
FACEBOOK_ACCESS_TOKEN
YOUTUBE_API_KEY
YOUTUBE_CHANNEL_ID
TIKTOK_ACCESS_TOKEN     # Optional — TikTok Research API
```

### Run Individual Steps
```bash
python tools/vimeo/fetch_transcripts.py --new-only
python tools/circle/fetch_posts.py
python tools/circle/fetch_posts.py --full
python tools/social/monitor.py
python tools/social/monitor.py --platform youtube
python tools/claude/generate_knowledge.py --days 90
python tools/claude/upload_knowledge.py --dry-run
python tools/claude/upload_knowledge.py
```

### Known Issues Resolved (in Cowork session)
- `fetch_posts.py` had encoding corruption on first file transfer — was re-transferred and confirmed correct (225 lines)
- GitHub direct push blocked from Cowork VM due to proxy — push must be done from Mac Terminal
- `vimeoscriptdownloader` naming used throughout earlier in session — now fully renamed
