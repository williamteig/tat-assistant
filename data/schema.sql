-- ============================================================
-- TAT Assistant — Supabase PostgreSQL Schema
-- Run this once in your Supabase SQL editor to set up all tables
-- ============================================================

-- ─── Vimeo Transcripts ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transcripts (
    id              TEXT PRIMARY KEY,           -- vimeo video ID
    title           TEXT NOT NULL,
    category        TEXT NOT NULL,              -- e.g. "Website Videos", "Livestreams"
    content         TEXT NOT NULL,              -- raw transcript text
    duration_secs   INTEGER,
    vimeo_url       TEXT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    in_knowledge    BOOLEAN NOT NULL DEFAULT FALSE  -- TRUE once included in latest upload
);

CREATE INDEX IF NOT EXISTS idx_transcripts_category ON transcripts(category);
CREATE INDEX IF NOT EXISTS idx_transcripts_in_knowledge ON transcripts(in_knowledge);

-- ─── Social Media Posts ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_posts (
    id              TEXT PRIMARY KEY,           -- platform:post_id  e.g. "instagram:abc123"
    platform        TEXT NOT NULL,              -- instagram | facebook | youtube | tiktok
    post_id         TEXT NOT NULL,
    caption         TEXT,
    media_type      TEXT,                       -- IMAGE | VIDEO | CAROUSEL_ALBUM | etc.
    permalink       TEXT,
    likes           INTEGER DEFAULT 0,
    comments_count  INTEGER DEFAULT 0,
    posted_at       TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    in_knowledge    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(platform, post_id)
);

CREATE INDEX IF NOT EXISTS idx_social_posts_platform ON social_posts(platform);
CREATE INDEX IF NOT EXISTS idx_social_posts_posted_at ON social_posts(posted_at DESC);

-- ─── Social Media Comments ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_comments (
    id              TEXT PRIMARY KEY,           -- platform:comment_id
    platform        TEXT NOT NULL,
    post_id         TEXT NOT NULL,              -- references social_posts.post_id
    comment_id      TEXT NOT NULL,
    author          TEXT,
    text            TEXT NOT NULL,
    likes           INTEGER DEFAULT 0,
    posted_at       TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(platform, comment_id)
);

CREATE INDEX IF NOT EXISTS idx_social_comments_post ON social_comments(platform, post_id);

-- ─── Circle Community Posts ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS circle_posts (
    id              TEXT PRIMARY KEY,           -- circle post ID (string)
    space_name      TEXT,                       -- which Space/Channel it was posted in
    author_name     TEXT,
    author_email    TEXT,
    title           TEXT,
    body            TEXT NOT NULL,
    post_url        TEXT,
    likes           INTEGER DEFAULT 0,
    comments_count  INTEGER DEFAULT 0,
    posted_at       TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    in_knowledge    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_circle_posts_space ON circle_posts(space_name);
CREATE INDEX IF NOT EXISTS idx_circle_posts_posted_at ON circle_posts(posted_at DESC);

-- ─── Circle Community Comments ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS circle_comments (
    id              TEXT PRIMARY KEY,           -- circle comment ID
    post_id         TEXT NOT NULL,              -- references circle_posts.id
    author_name     TEXT,
    body            TEXT NOT NULL,
    likes           INTEGER DEFAULT 0,
    posted_at       TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(id)
);

CREATE INDEX IF NOT EXISTS idx_circle_comments_post ON circle_comments(post_id);

-- ─── Claude Knowledge Sync Log ────────────────────────────────────────────────
-- Tracks which knowledge files have been uploaded to Claude and their file IDs
CREATE TABLE IF NOT EXISTS claude_sync_log (
    knowledge_file  TEXT PRIMARY KEY,           -- e.g. "transcripts_core.md"
    claude_file_id  TEXT,                       -- Anthropic Files API file ID
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row_count       INTEGER,                    -- how many records were in this upload
    file_size_bytes INTEGER
);
