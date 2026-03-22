"""
data/db.py — Supabase client helper
====================================
Central place to initialise the Supabase client so every tool imports
from here instead of duplicating connection logic.

Usage:
    from data.db import get_client
    sb = get_client()
    sb.table("transcripts").upsert({...}).execute()
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    """Return a cached Supabase client (initialised once per process)."""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")  # service role key — never expose publicly
        if not url or not key:
            raise EnvironmentError(
                "Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in environment. "
                "Check your .env file."
            )
        _client = create_client(url, key)
    return _client
