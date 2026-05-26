"""
post_social.py — Social Media Posting Module for Valarchi Reel Generator
=========================================================================

Handles posting to:
  ✅ Facebook  — Page video post via Graph API (uses public R2 URL)
  ✅ YouTube   — Video upload via YouTube Data API v3 resumable upload
                 (uploads local MP4 file — no extra library needed,
                  only `requests` which is already in requirements.txt)

  Instagram is handled separately in daily_run.py via post_to_instagram().

Required GitHub Secrets:
  Facebook:
    FB_PAGE_ID            — Facebook Page numeric ID
                            (find at facebook.com/YOUR_PAGE → About → Page ID)
    FB_PAGE_ACCESS_TOKEN  — Page-level access token with pages_manage_posts
                            + pages_read_engagement permissions
                            (generate via Meta Business Suite → Settings → API)

  YouTube:
    YOUTUBE_CLIENT_ID      — OAuth2 Client ID (Google Cloud Console)
    YOUTUBE_CLIENT_SECRET  — OAuth2 Client Secret
    YOUTUBE_REFRESH_TOKEN  — Long-lived refresh token
                             (generate once with get_youtube_token.py helper)

Usage:
  import post_social as ps

  # Facebook (needs public URL — e.g. from R2)
  ps.post_to_facebook(public_url, caption)

  # YouTube (uploads local MP4 file)
  ps.post_to_youtube(video_path, title, description, tags=["facts", "tamil"])
"""

import os
import time
import json
from pathlib import Path
import requests


# ─── FACEBOOK ──────────────────────────────────────────────────────────────

def post_to_facebook(video_url: str, caption: str) -> dict:
    """
    Post a video to a Facebook Page via Graph API.

    Facebook fetches the video from the public URL (Cloudflare R2) server-side,
    so no local file is needed.  The post goes to the Page's feed as a video.

    Required env vars: FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN

    Args:
        video_url: Public HTTPS URL of the MP4 (e.g. R2 CDN link)
        caption:   Post description text (hashtags included)

    Returns:
        dict with 'video_id' key on success
    """
    page_id = os.environ["FB_PAGE_ID"]
    token   = os.environ["FB_PAGE_ACCESS_TOKEN"]
    base    = "https://graph.facebook.com/v19.0"

    print("📘 Posting to Facebook Page…")

    resp = requests.post(
        f"{base}/{page_id}/videos",
        data={
            "file_url"    : video_url,
            "description" : caption,
            "title"       : caption.split("\n")[0][:100],   # first line as title
            "published"   : "true",
            "access_token": token,
        },
        timeout=120,
    )

    if not resp.ok:
        print(f"  [FB ERROR] {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    data     = resp.json()
    video_id = data.get("id")
    print(f"  ✅ Facebook video posted!  ID: {video_id}")
    print(f"     https://www.facebook.com/video/{video_id}")
    return {"video_id": video_id}


def build_facebook_caption(topic: dict) -> str:
    """Build a Facebook-optimised caption (same style as Instagram but slightly longer OK)."""
    title    = topic.get("title", topic["topic"])
    hashtags = topic.get("hashtags", "#தெரியுமா #தமிழ் #வளர்ச்சி")
    return (
        f"உங்களுக்கு தெரியுமா? 🤔\n\n"
        f"✨ {title}\n\n"
        f"💬 உங்கள் கருத்தை comment-ல் சொல்லுங்க!\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🔔 Like our page for daily Tamil facts!\n"
        f"❤️  Share this with someone curious!\n\n"
        f"{hashtags} #doyouknow2026 #tamilfacts #தமிழ் #didyouknow #reels"
    )


# ─── YOUTUBE ───────────────────────────────────────────────────────────────

def _refresh_youtube_token() -> str:
    """
    Exchange the long-lived refresh token for a short-lived access token.
    Hits Google's token endpoint directly — no google-auth library needed.
    """
    client_id     = os.environ["YOUTUBE_CLIENT_ID"]
    client_secret = os.environ["YOUTUBE_CLIENT_SECRET"]
    refresh_token = os.environ["YOUTUBE_REFRESH_TOKEN"]

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id"    : client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type"   : "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"YouTube token refresh failed: {data}")
    print("  🔑 YouTube access token refreshed OK")
    return data["access_token"]


def post_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: list = None,
    category_id: str = "27",    # 27 = Education  |  22 = People & Blogs  |  24 = Entertainment
    privacy: str = "public",
) -> dict:
    """
    Upload a local MP4 to YouTube via the resumable-upload API (no SDK needed).

    Required env vars: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

    Args:
        video_path:   Path to the local .mp4 file
        title:        YouTube video title (max 100 chars)
        description:  Full description (hashtags, links, etc.)
        tags:         List of tag strings
        category_id:  YouTube category numeric string
        privacy:      "public" | "unlisted" | "private"

    Returns:
        dict with 'video_id' and 'youtube_url'
    """
    print("▶️  Uploading to YouTube…")

    access_token = _refresh_youtube_token()

    file_size = video_path.stat().st_size
    print(f"  File: {video_path.name}  ({file_size / 1_048_576:.1f} MB)")

    # ── Step 1: Initiate resumable upload session ─────────────────────────
    metadata = {
        "snippet": {
            "title"       : title[:100],
            "description" : description,
            "tags"        : tags or ["didyouknow", "tamil", "doyouknow2026", "facts", "shorts"],
            "categoryId"  : category_id,
            "defaultLanguage": "ta",
        },
        "status": {
            "privacyStatus"          : privacy,
            "selfDeclaredMadeForKids": False,
            "madeForKids"            : False,
        },
    }

    init_resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization"           : f"Bearer {access_token}",
            "Content-Type"            : "application/json; charset=UTF-8",
            "X-Upload-Content-Type"   : "video/mp4",
            "X-Upload-Content-Length" : str(file_size),
        },
        json=metadata,
        timeout=30,
    )
    init_resp.raise_for_status()

    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("YouTube did not return a resumable upload URL.")

    print("  Upload session initiated — streaming file to YouTube…")

    # ── Step 2: Stream the MP4 to the upload URL ──────────────────────────
    CHUNK = 256 * 1024 * 1024   # 256 MB chunks (or whole file if smaller)

    with open(video_path, "rb") as fh:
        start = 0
        while start < file_size:
            chunk_data = fh.read(CHUNK)
            end        = start + len(chunk_data) - 1

            upload_resp = requests.put(
                upload_url,
                data=chunk_data,
                headers={
                    "Content-Type"  : "video/mp4",
                    "Content-Length": str(len(chunk_data)),
                    "Content-Range" : f"bytes {start}-{end}/{file_size}",
                },
                timeout=600,    # 10 min per chunk
            )

            # 308 = Resume Incomplete (more chunks needed)
            # 200 / 201 = Upload complete
            if upload_resp.status_code in (200, 201):
                break
            elif upload_resp.status_code == 308:
                start = end + 1
                print(f"  Chunk uploaded ({end / 1_048_576:.1f} MB / {file_size / 1_048_576:.1f} MB)")
            else:
                upload_resp.raise_for_status()

    response_data = upload_resp.json()
    video_id      = response_data.get("id")
    if not video_id:
        raise RuntimeError(f"YouTube upload response missing video ID: {response_data}")

    yt_url = f"https://youtu.be/{video_id}"
    print(f"  ✅ YouTube upload complete!  {yt_url}")
    print(f"     (processing may take a few minutes on YouTube's side)")
    return {"video_id": video_id, "youtube_url": yt_url}


def build_youtube_title(topic: dict) -> str:
    """
    Build a curiosity-driven YouTube Shorts title.

    Rotates through 7 hook patterns based on topic ID so no two
    consecutive videos share the same title format — this signals
    variety to the algorithm and tests which hooks get better CTR.

    Patterns alternate between:
      • Tamil-first (targets native Tamil speakers in Shorts feed)
      • English-first (boosts discoverability via YouTube search)
      • Shock/curiosity hooks (higher CTR in Shorts)
    """
    title    = topic.get("title", topic["topic"])
    topic_id = topic.get("id", 1)

    # 7 rotating hooks — (topic_id - 1) % 7 picks one
    HOOKS = [
        f"தெரியுமா? {title} 🤯 #Shorts",                          # 1 — Tamil curiosity
        f"Did You Know? {title} 😱 #Shorts",                       # 2 — English shock
        f"{title} — 99% பேருக்கு தெரியாது! 🤫 #Shorts",           # 3 — exclusivity hook
        f"Did You Know? {title} — Watch Till End! ⏩ #Shorts",      # 4 — retention hook
        f"இது தெரியுமா? {title} 😲 #Shorts",                      # 5 — Tamil question
        f"Did You Know? {title} 🧠 #Shorts",                       # 6 — knowledge hook
        f"அதிர்ச்சி உண்மை! {title} 🌟 #Shorts",                   # 7 — Tamil shock
    ]

    hook = HOOKS[(topic_id - 1) % len(HOOKS)]
    return hook[:100]


def build_youtube_description(topic: dict) -> str:
    """Build a rich YouTube description with chapters hint, hashtags, CTA."""
    title    = topic.get("title", topic["topic"])
    hashtags = topic.get("hashtags", "#தெரியுமா #தமிழ் #வளர்ச்சி")
    return (
        f"✨ {title}\n\n"
        f"Did you know this amazing fact? 🤔  Watch till the end!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔔 SUBSCRIBE for daily Tamil facts & amazing trivia!\n"
        f"👍 LIKE if you learned something new today!\n"
        f"💬 COMMENT — share this fact with a friend!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Follow us on Instagram & Facebook @doyou_know2026 for more!\n\n"
        f"{hashtags} "
        f"#doyouknow2026 #tamilfacts #didyouknow #shorts #ytshorts "
        f"#amazingfacts #தமிழ் #factsvideo #knowledgeshorts"
    )


# ─── ONE-TIME TOKEN HELPER (run locally, not in CI) ────────────────────────

def print_youtube_token_instructions():
    """
    Print instructions for getting a YouTube refresh token.
    Run this once locally; paste the refresh token into GitHub Secrets.
    """
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "YOUR_CLIENT_ID")
    scope     = "https://www.googleapis.com/auth/youtube.upload"
    auth_url  = (
        f"https://accounts.google.com/o/oauth2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
        f"&scope={scope}"
        f"&response_type=code"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    print("\n" + "="*60)
    print("  YouTube One-Time Token S