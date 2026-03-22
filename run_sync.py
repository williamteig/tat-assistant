#!/usr/bin/env python3
"""
run_sync.py — TAT Assistant Orchestrator
==========================================
Runs the full sync pipeline in sequence:

  1. Fetch new Vimeo transcripts  →  Supabase
  2. Fetch new Circle posts        →  Supabase
  3. Fetch new social media posts  →  Supabase
  4. Generate consolidated knowledge documents
  5. Upload documents to Anthropic Files API

Each step is independent — a failure in one step is logged but does not
stop the others. At the end a summary is printed.

Usage:
    python run_sync.py                     # full pipeline
    python run_sync.py --skip-upload       # skip Anthropic upload (dry test)
    python run_sync.py --full              # ignore watermarks, re-fetch everything
    python run_sync.py --only vimeo        # run only one step
    python run_sync.py --only vimeo circle # run specific steps
"""

import argparse
import sys
import traceback
from datetime import datetime, timezone

# ─── Step definitions ──────────────────────────────────────────────────────────

STEPS = ["vimeo", "circle", "social", "generate", "upload"]


def run_vimeo(full: bool):
    from tools.vimeo.fetch_transcripts import main as vimeo_main
    # Patch sys.argv to pass --new-only when not doing full re-fetch
    old_argv = sys.argv
    sys.argv = ["fetch_transcripts.py"] + ([] if full else ["--new-only"])
    try:
        vimeo_main()
    finally:
        sys.argv = old_argv


def run_circle(full: bool):
    from tools.circle.fetch_posts import main as circle_main
    old_argv = sys.argv
    sys.argv = ["fetch_posts.py"] + (["--full"] if full else [])
    try:
        circle_main()
    finally:
        sys.argv = old_argv


def run_social(full: bool):
    from tools.social.monitor import main as social_main
    old_argv = sys.argv
    sys.argv = ["monitor.py"] + (["--full"] if full else [])
    try:
        social_main()
    finally:
        sys.argv = old_argv


def run_generate():
    from tools.claude.generate_knowledge import main as gen_main
    old_argv = sys.argv
    sys.argv = ["generate_knowledge.py"]
    try:
        gen_main()
    finally:
        sys.argv = old_argv


def run_upload(dry_run: bool):
    from tools.claude.upload_knowledge import main as upload_main
    old_argv = sys.argv
    sys.argv = ["upload_knowledge.py"] + (["--dry-run"] if dry_run else [])
    try:
        upload_main()
    finally:
        sys.argv = old_argv


RUNNERS = {
    "vimeo":    lambda args: run_vimeo(args.full),
    "circle":   lambda args: run_circle(args.full),
    "social":   lambda args: run_social(args.full),
    "generate": lambda args: run_generate(),
    "upload":   lambda args: run_upload(args.skip_upload),
}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TAT Assistant — full sync pipeline")
    parser.add_argument("--full", action="store_true",
                        help="Re-fetch everything, ignoring watermarks")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Skip the Anthropic upload step (generate docs only)")
    parser.add_argument("--only", nargs="+", choices=STEPS, metavar="STEP",
                        help=f"Run only these steps: {', '.join(STEPS)}")
    args = parser.parse_args()

    steps_to_run = args.only if args.only else STEPS
    # If --skip-upload, remove upload from steps
    if args.skip_upload and "upload" in steps_to_run:
        steps_to_run = [s for s in steps_to_run if s != "upload"]

    started_at = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"  TAT Assistant Sync — {started_at.strftime('%d %b %Y %H:%M UTC')}")
    print(f"  Steps: {', '.join(steps_to_run)}")
    if args.full:
        print("  Mode: FULL RE-FETCH")
    print(f"{'='*60}\n")

    results: dict[str, str] = {}

    for step in steps_to_run:
        print(f"\n{'─'*60}")
        print(f"  STEP: {step.upper()}")
        print(f"{'─'*60}")
        try:
            RUNNERS[step](args)
            results[step] = "✓ OK"
        except SystemExit as e:
            results[step] = f"✗ Exited ({e.code})"
        except Exception:
            results[step] = "✗ ERROR"
            traceback.print_exc()

    # Summary
    duration = (datetime.now(timezone.utc) - started_at).seconds
    print(f"\n{'='*60}")
    print(f"  SYNC COMPLETE  ({duration}s)")
    print(f"{'='*60}")
    for step, status in results.items():
        print(f"  {step:<12} {status}")
    print(f"{'='*60}\n")

    # Exit non-zero if any step failed
    if any("✗" in s for s in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
