# theauditiontechnique-helper

A toolkit for managing and automating the business operations of **The Audition Technique** — Greg Apps' actor training and membership business.

## Structure

```
theauditiontechnique-helper/
├── sync.py               # 2-way sync: Markdown files ↔ Notion Business Hub
├── sync_map.json         # Maps each MD file to its Notion page ID
├── requirements.txt      # Python dependencies
│
├── business/             # Business function docs (synced with Notion)
│   ├── value-ladder.md
│   ├── support-system.md
│   ├── team.md
│   ├── content-strategy.md
│   ├── membership-site.md
│   ├── brand-messaging.md
│   ├── revenue-model.md
│   ├── course-curriculum.md
│   └── launch-campaigns.md
│
└── tools/
    └── vimeo/            # Vimeo transcript downloader
        ├── download_transcripts.py
        └── transcripts/
```

## Business Hub Sync

All files in `business/` are 2-way synced with the **Business Hub** database in Notion (under The Audition Technique page).

### Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Add your Notion API key to `.env`:
   ```
   NOTION_API_KEY=secret_...
   ```
   Get one at https://www.notion.so/my-integrations — make sure to connect it to the TAT workspace.

3. Run an initial push to populate Notion with your local files:
   ```
   python sync.py --push
   ```

### Usage

```bash
python sync.py              # Auto-detect direction for each file
python sync.py --push       # Force push all MD files → Notion
python sync.py --pull       # Force pull all Notion pages → MD files
python sync.py --status     # Show what needs syncing (no changes made)
python sync.py --file business/team.md  # Sync a single file
```

### How direction is determined (auto mode)

| Situation | Action |
|-----------|--------|
| Never synced before | Push MD → Notion |
| MD edited more recently than last sync | Push MD → Notion |
| Notion edited more recently than last sync | Pull Notion → MD |
| Both changed since last sync | ⚠ Conflict — skipped, marked in Notion |
| Neither changed | Already in sync, skip |

---

## Vimeo Transcript Downloader

Downloads all transcripts/captions from every video in the Vimeo account as plain `.txt` files.

### Setup

1. Add your Vimeo Personal Access Token to `.env`:
   ```
   VIMEO_ACCESS_TOKEN=...
   ```
   Generate one at https://developer.vimeo.com/apps — make sure to enable the `private` scope.

### Usage

```
python tools/vimeo/download_transcripts.py
```

Transcripts are saved in `tools/vimeo/transcripts/`, organised by Vimeo folder.
