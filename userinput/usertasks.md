# User Tasks — TAT Assistant Setup

Tasks to complete before the app is fully operational.

---

## 1. Supabase (Database)

- [ ] Create a free project at https://supabase.com
- [ ] Go to SQL Editor, paste the contents of `data/schema.sql` and run it
- [ ] Go to Project Settings → API and copy:
  - Project URL → `SUPABASE_URL`
  - `service_role` key (not the anon key) → `SUPABASE_SERVICE_KEY`

---

## 2. Anthropic / Claude

- [ ] Generate an API key at https://console.anthropic.com → API Keys → `ANTHROPIC_API_KEY`
- [ ] Open the TAT Claude project and copy the ID from the URL (`claude.ai/project/XXXXXXXX`) → `CLAUDE_PROJECT_ID`

---

## 3. Vimeo

- [ ] Go to https://developer.vimeo.com/apps and create or open an app
- [ ] Generate a Personal Access Token with the `private` scope → `VIMEO_ACCESS_TOKEN`

---

## 4. Circle

- [ ] In Circle dashboard go to Settings → API and generate a token → `CIRCLE_API_TOKEN`
- [ ] Note your community subdomain (e.g. `theauditiontechnique` from `theauditiontechnique.circle.so`) → `CIRCLE_COMMUNITY_SLUG`
- [ ] Optionally note specific Space IDs to limit what gets fetched → `CIRCLE_SPACE_IDS`

---

## 5. Instagram & Facebook (Meta Graph API)

- [ ] Go to https://developers.facebook.com and create an app (type: Business)
- [ ] Add the **Instagram Graph API** and **Pages API** products to the app
- [ ] Connect the TAT Facebook Page and Instagram account
- [ ] Generate a long-lived Page Access Token → `FACEBOOK_ACCESS_TOKEN`
- [ ] Copy the Facebook Page ID → `FACEBOOK_PAGE_ID`
- [ ] Copy the Instagram Business Account ID → `INSTAGRAM_ACCOUNT_ID`
- [ ] The Instagram Access Token is the same as the Facebook Page Access Token → `INSTAGRAM_ACCESS_TOKEN`

---

## 6. YouTube

- [ ] Go to https://console.cloud.google.com → Create a project
- [ ] Enable the **YouTube Data API v3**
- [ ] Create an API key (Credentials → Create Credentials → API Key) → `YOUTUBE_API_KEY`
- [ ] Copy the TAT YouTube Channel ID (visible in channel URL or Settings) → `YOUTUBE_CHANNEL_ID`

---

## 7. TikTok (optional)

- [ ] Apply for TikTok Research API access at https://developers.tiktok.com (requires approval)
- [ ] Once approved, generate an access token → `TIKTOK_ACCESS_TOKEN`

---

## 8. Local .env file

- [ ] Copy `.env.example` to `.env` in the project root
- [ ] Fill in all values gathered above
- [ ] Confirm `.env` is in `.gitignore` (it is — do not commit it)

---

## 9. GitHub Secrets (for automated sync)

- [ ] Go to repo Settings → Secrets and variables → Actions
- [ ] Add each variable from `.env` as a repository secret using the exact same name
- [ ] Trigger the workflow manually once (Actions tab → TAT Knowledge Sync → Run workflow) to verify it works

---

## 10. First local test run

- [ ] Run `pip install -r requirements.txt`
- [ ] Run `python run_sync.py --full --skip-upload` — fetches everything, generates knowledge docs, does NOT upload to Claude
- [ ] Check the `knowledge/` folder for 4 generated `.md` files
- [ ] If happy, run `python run_sync.py --full` to do the full run including Claude upload
