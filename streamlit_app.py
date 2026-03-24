"""
TAT Assistant — Streamlit Web Interface
========================================
Tab 1: Chat  — ask questions answered from Greg's full content library
Tab 2: Data  — browse all transcripts and posts stored in Supabase

Run:  .venv/bin/streamlit run streamlit_app.py
"""

import anthropic
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TAT Assistant",
    page_icon="🎭",
    layout="wide",
)

# ─── Shared clients ───────────────────────────────────────────────────────────

@st.cache_resource
def get_db():
    from data.db import get_client
    return get_client()

@st.cache_resource
def get_anthropic():
    return anthropic.Anthropic()

# ─── Knowledge file IDs ───────────────────────────────────────────────────────

@st.cache_data(ttl=300)  # refresh every 5 minutes
def load_file_ids() -> dict[str, str]:
    """Load current file IDs from claude_sync_log in Supabase."""
    try:
        sb = get_db()
        rows = sb.table("claude_sync_log").select("knowledge_file,claude_file_id").execute()
        return {r["knowledge_file"]: r["claude_file_id"] for r in (rows.data or [])
                if r.get("claude_file_id")}
    except Exception as e:
        st.warning(f"Could not load file IDs from Supabase: {e}")
        return {}

# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the TAT Assistant — a knowledgeable guide for The Audition Technique, \
created by casting director Greg Apps. You answer questions about Greg's teaching methodology, \
audition techniques, content, and community based solely on the provided knowledge documents.

Greg's core philosophy: audition success comes from creating a distinctive, memorable character — \
not from perfecting a technically correct performance. Actors must take ownership of their creative \
choices, embrace risk and experimentation, and measure progress by the quality of their character \
work rather than by bookings.

Answer clearly and directly. When quoting or referencing specific content, say where it came from \
(e.g. "In the livestream on indicating..." or "In the Self Taping Academy course..."). \
If the answer isn't in the provided documents, say so rather than making something up."""

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab_chat, tab_data = st.tabs(["💬  Chat", "📊  Data"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — CHAT
# ══════════════════════════════════════════════════════════════════════════════

with tab_chat:
    st.title("TAT Assistant")
    st.caption("Ask anything about Greg Apps' teaching methodology, content, or community.")

    # Initialise chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Load file IDs
    file_ids = load_file_ids()

    if not file_ids:
        st.error("No knowledge documents found. Run the sync pipeline first: "
                 "`python run_sync.py --only vimeo generate upload`")
    else:
        # Show which knowledge docs are loaded
        with st.expander(f"Knowledge loaded ({len(file_ids)} documents)", expanded=False):
            for fname, fid in file_ids.items():
                st.code(f"{fname}  →  {fid}", language=None)

    # Render chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask a question about Greg's teaching..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Build document blocks from file IDs
        document_blocks = []
        for fname, fid in file_ids.items():
            document_blocks.append({
                "type": "document",
                "source": {"type": "file", "file_id": fid},
                "title": fname.replace(".md", "").replace("_", " ").title(),
            })

        # Build message content — documents first, then the question
        content = document_blocks + [{"type": "text", "text": prompt}]

        # Build full conversation for context (last 10 turns)
        history = st.session_state.messages[:-1]  # exclude current user message
        api_messages = []
        for m in history[-10:]:
            api_messages.append({"role": m["role"], "content": m["content"]})
        api_messages.append({"role": "user", "content": content})

        # Call Claude
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    client = get_anthropic()
                    response = client.beta.messages.create(
                        model="claude-opus-4-6",
                        max_tokens=2048,
                        system=SYSTEM_PROMPT,
                        messages=api_messages,
                        betas=["files-api-2025-04-14"],
                    )
                    reply = response.content[0].text
                except Exception as e:
                    reply = f"Error calling Claude API: {e}"

            st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})

    # Clear chat button
    if st.session_state.messages:
        if st.button("Clear conversation"):
            st.session_state.messages = []
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DATA VIEWER
# ══════════════════════════════════════════════════════════════════════════════

with tab_data:
    st.title("Data Browser")
    st.caption("All content synced into Supabase.")

    try:
        sb = get_db()

        # ── Summary stats ──────────────────────────────────────────────────────
        transcripts_resp = sb.table("transcripts").select("id,category").execute()
        circle_resp      = sb.table("circle_posts").select("id").execute()
        social_resp      = sb.table("social_posts").select("id,platform").execute()

        transcripts_all = transcripts_resp.data or []
        circle_all      = circle_resp.data or []
        social_all      = social_resp.data or []

        col1, col2, col3 = st.columns(3)
        col1.metric("Vimeo Transcripts", len(transcripts_all))
        col2.metric("Circle Posts", len(circle_all))
        col3.metric("Social Posts", len(social_all))

        st.divider()

        # ── Transcripts ────────────────────────────────────────────────────────
        st.subheader("Vimeo Transcripts")

        if not transcripts_all:
            st.info("No transcripts yet. Run the Vimeo sync step.")
        else:
            # Group by category
            categories: dict[str, list] = {}
            for r in transcripts_all:
                categories.setdefault(r["category"], []).append(r)

            # Category filter
            all_cats = sorted(categories.keys())
            selected = st.multiselect("Filter by category", all_cats, default=all_cats)

            # Fetch full data for selected categories
            full_resp = sb.table("transcripts")\
                .select("id,title,category,duration_secs,vimeo_url,fetched_at")\
                .in_("category", selected)\
                .order("category")\
                .execute()
            rows = full_resp.data or []

            for row in rows:
                duration = f"{row['duration_secs'] // 60}m {row['duration_secs'] % 60}s" \
                           if row.get("duration_secs") else "—"
                label = f"**{row['title']}** · {row['category']} · {duration}"
                with st.expander(label):
                    st.write(f"**Vimeo ID:** `{row['id']}`")
                    if row.get("vimeo_url"):
                        st.write(f"**URL:** {row['vimeo_url']}")
                    st.write(f"**Fetched:** {row['fetched_at'][:10]}")
                    # Load transcript content on demand
                    if st.button("Load transcript", key=f"t_{row['id']}"):
                        content_resp = sb.table("transcripts")\
                            .select("content")\
                            .eq("id", row["id"])\
                            .single()\
                            .execute()
                        st.text_area("Transcript", content_resp.data["content"],
                                     height=300, key=f"ta_{row['id']}")

        st.divider()

        # ── Circle posts ───────────────────────────────────────────────────────
        st.subheader("Circle Community Posts")

        if not circle_all:
            st.info("No Circle posts yet. Add Circle credentials and run the Circle sync step.")
        else:
            circle_full = sb.table("circle_posts")\
                .select("id,title,author_name,space_name,posted_at,comments_count")\
                .order("posted_at", desc=True)\
                .limit(100)\
                .execute()
            for row in (circle_full.data or []):
                label = f"**{row.get('title') or '(no title)'}** · {row.get('space_name','')} " \
                        f"· {row.get('author_name','')} · 💬 {row.get('comments_count',0)}"
                with st.expander(label):
                    st.write(f"**Posted:** {str(row.get('posted_at',''))[:10]}")
                    if st.button("Load post", key=f"c_{row['id']}"):
                        post = sb.table("circle_posts").select("body")\
                            .eq("id", row["id"]).single().execute()
                        st.markdown(post.data["body"])

        st.divider()

        # ── Social posts ───────────────────────────────────────────────────────
        st.subheader("Social Media Posts")

        if not social_all:
            st.info("No social posts yet. Add Facebook/Instagram credentials and run the social sync step.")
        else:
            platforms = sorted({r["platform"] for r in social_all})
            selected_platform = st.selectbox("Platform", ["All"] + platforms)

            query = sb.table("social_posts")\
                .select("id,platform,caption,posted_at,likes,comments_count,permalink")\
                .order("posted_at", desc=True)\
                .limit(100)
            if selected_platform != "All":
                query = query.eq("platform", selected_platform)
            social_full = query.execute()

            for row in (social_full.data or []):
                caption_preview = (row.get("caption") or "")[:80]
                label = f"**{row['platform']}** · {caption_preview}… · ❤️ {row.get('likes',0)}"
                with st.expander(label):
                    st.write(f"**Posted:** {str(row.get('posted_at',''))[:10]}")
                    st.write(row.get("caption", ""))
                    if row.get("permalink"):
                        st.write(f"**Link:** {row['permalink']}")

    except Exception as e:
        st.error(f"Could not connect to Supabase: {e}")
        st.info("Make sure your `.env` file has `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` set.")
