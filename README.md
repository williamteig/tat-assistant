# Vimeo Transcript Downloader

Downloads all transcripts/captions from every video in your Vimeo account as plain `.txt` files.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Create a `.env` file (copy from `.env.example`):
   ```
   cp .env.example .env
   ```

3. Add your Vimeo Personal Access Token to `.env`. Generate one at https://developer.vimeo.com/apps — make sure to enable the `private` scope.

## Usage

```
python download_transcripts.py
```

Transcripts are saved as `.txt` files in the `transcripts/` directory, named after each video title. Videos without transcripts are skipped.
