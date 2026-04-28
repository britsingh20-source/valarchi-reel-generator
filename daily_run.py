"""
daily_run.py — Valarchi Auto-Reel Pipeline
==========================================
Picks today's "Did You Know" topic from topics.json (cycles through all topics),
fetches a relevant B-roll video from Pixabay, generates a 1080x1920 Tamil reel
video with TTS voiceover, uploads to Cloudflare R2, and posts to Instagram.

Cloudflare R2 Free Tier:
  ✅  10 GB storage
  ✅  1 million uploads/month
  ✅  ZERO egress (bandwidth) fees

GitHub Secrets required:
  PIXABAY_API_KEY         — Pixabay API key (free at pixabay.com/api/docs)
  CF_ACCOUNT_ID           — Cloudflare Account ID
  CF_R2_ACCESS_KEY_ID     — R2 API Token → Access Key ID
  CF_R2_SECRET_ACCESS_KEY — R2 API Token → Secret Access Key
  CF_R2_BUCKET_NAME       — R2 bucket name  (e.g. valarchi-reels)
  CF_R2_PUBLIC_URL        — Public URL base (e.g. https://pub-xxxx.r2.dev)
  INSTAGRAM_USER_ID       — IG Business account numeric ID
  IG_ACCESS_TOKEN         — Long-lived Graph API access token

Run locally:
    python3 daily_run.py               # auto day from state.json
    python3 daily_run.py --day 5       # force topic #5
    python3 daily_run.py --dry-run     # generate video, skip upload & post
"""

import os, sys, json, time, argparse
from pathlib import Path
from datetime import datetime

import requests

# ─── local module ─────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
import generate_reel as gr

# ─── paths ─────────────────────────────────────────────────────────────────
BASE        = Path(__file__).parent
TOPICS_FILE = BASE / "topics.json"
STATE_FILE  = BASE / "state.json"
BG_DIR      = BASE / "backgrounds"
OUTPUT_DIR  = BASE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ─── helpers ───────────────────────────────────────────────────────────────
def load_topics():
    with open(TOPICS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"day": 0, "posted": []}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def pick_topic(topics: list, state: dict, force_day: int = None):
    day   = force_day if force_day is not None else state["day"]
    idx   = day % len(topics)
    topic = topics[idx]
    print(f"📅  Day {day + 1}  →  Topic #{topic['id']}: {topic['topic']}")
    return topic, day


def pick_background():
    """Return first available background video, or None."""
    if BG_DIR.exists():
        for ext in ("*.mp4", "*.mov", "*.avi", "*.mkv"):
            vids = list(BG_DIR.glob(ext))
            if vids:
                return vids[0]
    return None


# ─── PIXABAY B-ROLL FETCHER ────────────────────────────────────────────────
# Topic → list of 5 related search queries (used one-per-clip for variety)
TOPIC_QUERIES = {
    "rubber"      : ["rubber plantation", "rubber tree tapping", "latex rubber tree", "tropical jungle trees", "rubber production factory"],
    "honey"       : ["honeybee collecting nectar", "beehive honeycomb", "bees on flowers", "honey flowing golden", "beekeeper hive"],
    "salt"        : ["salt harvest flats", "salt pans aerial", "salt mine", "seawater evaporation", "salt farmer"],
    "silk"        : ["silk fabric weaving", "silkworm cocoon", "silk loom traditional", "silk thread production", "silk textile India"],
    "coconut"     : ["coconut tree", "coconut water drinking", "coconut harvest farm", "palm tree tropical", "coconut plantation"],
    "rice"        : ["rice paddy field", "rice harvest farmers", "rice terraces green", "rice grain farming", "paddy cultivation"],
    "glass"       : ["glass blowing artist", "molten glass factory", "glass production", "sand melting", "glass manufacturing"],
    "coffee"      : ["coffee plantation farm", "coffee beans harvest", "espresso coffee brewing", "barista making coffee", "coffee roasting"],
    "ocean"       : ["ocean underwater coral", "sea waves aerial", "deep ocean blue", "coral reef fish", "ocean surface sunrise"],
    "sleep"       : ["person sleeping bed", "brain activity science", "night sky stars", "alarm clock morning", "deep sleep"],
    "spider"      : ["spider web morning dew", "spider spinning web", "spider web macro", "spider silk close", "spider nature macro"],
    "banana"      : ["banana plantation", "banana tree tropical", "banana bunch harvesting", "tropical fruit farm", "banana leaves"],
    "lightning"   : ["lightning storm night", "thunderstorm lightning bolt", "storm clouds dramatic", "lightning strike", "thunder rain storm"],
    "fingerprint" : ["fingerprint biometric scan", "fingerprint scanning technology", "security fingerprint digital", "fingerprint close up", "identity verification tech"],
    "heart"       : ["heartbeat monitor hospital", "heart surgery medical", "human heart anatomy", "cardiology doctor", "ECG heart monitor"],
    "brain"       : ["brain neuron synapse", "brain MRI scan", "neuroscience research lab", "brain neural network", "human brain anatomy"],
    "water"       : ["water drop slow motion", "river flowing clean", "water ripple surface", "fresh water nature", "waterfall clean water"],
    "sun"         : ["sunrise golden hour", "sunlight forest rays", "solar energy sun", "sunset sky orange", "sun rays nature"],
    "moon"        : ["full moon night sky", "moon craters telescope", "moonrise ocean", "lunar surface", "moon phases"],
    "diamond"     : ["diamond gemstone sparkle", "gem cutting diamond", "crystal mineral geology", "diamond jewelry close", "precious stone mining"],
    # Additional topics
    "fire"        : ["fire flames burning", "wildfire forest", "campfire night", "fire close macro", "volcanic lava fire"],
    "earthquake"  : ["earthquake damage building", "seismic activity ground", "earthquake ruins", "tectonic plates science", "earthquake aftermath"],
    "volcano"     : ["volcano eruption lava", "lava flow volcanic", "volcanic ash eruption", "magma lava rocks", "volcano crater aerial"],
    "tornado"     : ["tornado storm wind", "twister funnel cloud", "tornado destruction", "storm chaser tornado", "cyclone wind storm"],
    "gravity"     : ["space astronaut floating", "apple falling gravity", "physics science experiment", "gravity wave science", "weightless space"],
    "light"       : ["light refraction prism", "sunlight beam rays", "light speed science", "laser beam light", "rainbow light spectrum"],
    "sound"       : ["sound wave visualization", "music instruments playing", "sound frequency wave", "speaker vibration sound", "acoustic sound music"],
    "electricity" : ["electricity lightning bolt", "power lines energy", "electrical circuit board", "electricity arc blue", "power plant energy"],
    "internet"    : ["server data center", "internet fiber optic", "network cables data", "cyber technology digital", "computer network server"],
    "plant"       : ["plant growing timelapse", "seed germination roots", "green plant leaves", "photosynthesis sunlight plant", "nature plant growth"],
    "blood"       : ["blood cells microscope", "medical laboratory blood", "heartbeat blood flow", "red blood cells", "medical science biology"],
    "eye"         : ["human eye close up", "eye iris macro", "vision eye science", "optometry eye check", "eye pupil dilate"],
    "ant"         : ["ant colony work", "ants carrying food", "ant nest underground", "ant macro close up", "insect colony ants"],
    "whale"       : ["whale ocean swimming", "blue whale underwater", "whale breach ocean", "humpback whale", "ocean whale migration"],
    "tree"        : ["tree forest aerial", "old giant tree", "forest canopy drone", "tree roots nature", "ancient forest trees"],
    "cloud"       : ["clouds sky timelapse", "storm clouds forming", "cumulus clouds blue sky", "cloud formation aerial", "sky clouds dramatic"],
    "earthquake"  : ["earthquake seismic", "building collapse disaster", "tectonic fault line", "earthquake aftermath", "seismograph recording"],
    "coral"       : ["coral reef underwater", "coral bleaching ocean", "tropical fish coral", "scuba diving reef", "marine life coral"],
    "migration"   : ["bird migration flock", "wildebeest migration", "bird flock sky", "animal migration herd", "salmon river migration"],
    "bacteria"    : ["bacteria microscope science", "microbiology lab research", "petri dish bacteria culture", "microorganism science", "medical microscopy"],
}

# Default queries for topics not in the list above
DEFAULT_QUERIES = [
    "nature science facts",
    "earth environment aerial",
    "science laboratory research",
    "technology innovation future",
    "world discovery amazing",
]

def _get_topic_queries(topic: str) -> list:
    """Return 5 related search queries for a topic."""
    topic_lower = topic.lower().replace(" ", "_")
    if topic_lower in TOPIC_QUERIES:
        return TOPIC_QUERIES[topic_lower]
    # Try partial match
    for key in TOPIC_QUERIES:
        if key in topic_lower or topic_lower in key:
            return TOPIC_QUERIES[key]
    # Fallback: use topic name + generic science
    return [f"{topic} nature", f"{topic} science", f"{topic} close up",
            "nature documentary aerial", "science discovery facts"]

def _dl_one_pexels(api_key: str, query: str, used_ids: set):
    """Download one Pexels video for query, skipping used_ids. Returns Path or None."""
    import random
    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 15, "size": "medium"},
            timeout=15,
        )
        resp.raise_for_status()
        hits = [v for v in resp.json().get("videos", []) if v["id"] not in used_ids]
        if not hits:
            return None
        video  = random.choice(hits[:8])
        vid_id = video["id"]
        cached = BG_DIR / f"pexels_{vid_id}.mp4"
        if cached.exists() and cached.stat().st_size > 100_000:
            print(f"   Cached: pexels_{vid_id}.mp4")
            used_ids.add(vid_id)
            return cached
        # Pick best quality HD file
        files = video.get("video_files", [])
        # Prefer hd quality, mp4
        hd = [f for f in files if f.get("quality") == "hd" and "mp4" in f.get("file_type","")]
        sd = [f for f in files if f.get("quality") in ("sd","") and "mp4" in f.get("file_type","")]
        pick = (hd or sd or files)
        if not pick:
            return None
        url = pick[0]["link"]
        print(f"   Downloading pexels_{vid_id}.mp4 from '{query}'...")
        dl = requests.get(url, timeout=90, stream=True)
        dl.raise_for_status()
        with open(cached, "wb") as f:
            for chunk in dl.iter_content(chunk_size=256 * 1024):
                f.write(chunk)
        size_mb = cached.stat().st_size / 1048576
        print(f"   [OK] {size_mb:.1f} MB")
        used_ids.add(vid_id)
        return cached
    except Exception as e:
        print(f"   [WARN pexels] {e}")
        return None


def _dl_one_pixabay(api_key: str, query: str, used_ids: set):
    """Download one Pixabay video for query, skipping used_ids. Returns Path or None."""
    import random
    try:
        resp = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": api_key, "q": query, "video_type": "film",
                    "per_page": 15, "safesearch": "true"},
            timeout=15,
        )
        resp.raise_for_status()
        hits = [h for h in resp.json().get("hits", []) if h["id"] not in used_ids]
        if not hits:
            return None
        video  = random.choice(hits[:8])
        vid_id = video["id"]
        cached = BG_DIR / f"pixabay_{vid_id}.mp4"
        if cached.exists() and cached.stat().st_size > 100_000:
            print(f"   Cached: pixabay_{vid_id}.mp4")
            used_ids.add(vid_id)
            return cached
        videos = video.get("videos", {})
        url = (videos.get("medium", {}).get("url") or
               videos.get("small",  {}).get("url") or
               videos.get("large",  {}).get("url"))
        if not url:
            return None
        print(f"   Downloading pixabay_{vid_id}.mp4 from '{query}'...")
        dl = requests.get(url, timeout=60, stream=True)
        dl.raise_for_status()
        with open(cached, "wb") as f:
            for chunk in dl.iter_content(chunk_size=256 * 1024):
                f.write(chunk)
        print(f"   [OK] {cached.stat().st_size/1048576:.1f} MB")
        used_ids.add(vid_id)
        return cached
    except Exception as e:
        print(f"   [WARN pixabay] {e}")
        return None


def fetch_broll(topic: str, count: int = 5) -> list:
    """
    Fetch `count` topic-relevant B-roll videos.
    Tries Pexels first (better relevance), falls back to Pixabay, then cached files.
    """
    pexels_key  = os.environ.get("PEXELS_API_KEY", "")
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "")

    BG_DIR.mkdir(exist_ok=True)

    queries  = _get_topic_queries(topic)
    while len(queries) < count:
        queries.append(f"{topic} nature")

    results  = []
    used_ids = set()

    # ── 1. Try Pexels (primary — better topic relevance) ───────────────
    if pexels_key:
        print(f"[pexels] Fetching {count} B-roll clips for '{topic}'")
        for q in queries:
            if len(results) >= count:
                break
            path = _dl_one_pexels(pexels_key, q, used_ids)
            if path:
                results.append(path)
        print(f"[pexels] Got {len(results)} clip(s)")

    # ── 2. Fill remaining slots with Pixabay ───────────────────────────
    if len(results) < count and pixabay_key:
        needed = count - len(results)
        print(f"[pixabay] Fetching {needed} more clip(s) for '{topic}'")
        for q in queries:
            if len(results) >= count:
                break
            path = _dl_one_pixabay(pixabay_key, q, used_ids)
            if path and path not in results:
                results.append(path)

    # ── 3. Last resort: use whatever is cached in backgrounds/ ─────────
    if not results:
        print("[broll] No API keys or all downloads failed — using cached backgrounds")
        return list(BG_DIR.glob("*.mp4"))[:count]

    print(f"[broll] Ready: {len(results)} B-roll video(s)")
    return results


# Keep old name as alias so nothing else breaks
def fetch_pixabay_broll(topic: str, count: int = 5) -> list:
    return fetch_broll(topic, count)


# ─── CLOUDFLARE R2 UPLOAD ──────────────────────────────────────────────────
def upload_to_r2(video_path: Path) -> str:
    """Upload MP4 to Cloudflare R2. Returns public HTTPS URL."""
    import boto3
    from botocore.config import Config

    account_id  = os.environ["CF_ACCOUNT_ID"]
    access_key  = os.environ["CF_R2_ACCESS_KEY_ID"]
    secret_key  = os.environ["CF_R2_SECRET_ACCESS_KEY"]
    bucket      = os.environ["CF_R2_BUCKET_NAME"]
    public_base = os.environ["CF_R2_PUBLIC_URL"].rstrip("/")

    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3",
        endpoint_url          = endpoint,
        aws_access_key_id     = access_key,
        aws_secret_access_key = secret_key,
        config = Config(signature_version="s3v4", region_name="auto"),
    )

    fname   = video_path.name
    obj_key = f"reels/{fname}"

    print(f"☁️   Uploading → {bucket}/{obj_key} …")
    with open(video_path, "rb") as fh:
        s3.upload_fileobj(
            fh, bucket, obj_key,
            ExtraArgs={"ContentType": "video/mp4", "CacheControl": "public, max-age=86400"},
        )

    public_url = f"{public_base}/{obj_key}"
    print(f"✅  R2 URL: {public_url}")
    return public_url


# ─── INSTAGRAM GRAPH API ───────────────────────────────────────────────────
def post_to_instagram(video_url: str, caption: str) -> dict:
    """Post a Reel via Instagram Graph API. Returns dict with post_id."""
    user_id = os.environ["INSTAGRAM_USER_ID"]
    token   = os.environ["IG_ACCESS_TOKEN"]
    base    = "https://graph.facebook.com/v19.0"

    # Step 1 — create media container
    print("📤  Creating Instagram Reel container…")
    resp = requests.post(
        f"{base}/{user_id}/media",
        data={
            "media_type"   : "REELS",
            "video_url"    : video_url,
            "caption"      : caption,
            "share_to_feed": "true",
            "access_token" : token,
        },
        timeout=60,
    )
    resp.raise_for_status()
    container_id = resp.json()["id"]
    print(f"   Container ID: {container_id}")

    # Step 2 — wait for processing (up to 5 min)
    print("⏳  Waiting for Instagram to process video…")
    for attempt in range(30):
        time.sleep(10)
        sr = requests.get(
            f"{base}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        sr.raise_for_status()
        status = sr.json().get("status_code", "")
        print(f"   [{attempt+1}/30] status: {status}")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError(f"Instagram processing error: {sr.json()}")
    else:
        raise TimeoutError("Instagram video processing timed out after 5 minutes.")

    # Step 3 — publish
    print("🚀  Publishing Reel…")
    pub = requests.post(
        f"{base}/{user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    pub.raise_for_status()
    post_id = pub.json()["id"]
    print(f"✅  Published! Post ID: {post_id}")
    return {"post_id": post_id, "container_id": container_id}


# ─── BUILD INSTAGRAM CAPTION ───────────────────────────────────────────────
def build_caption(topic: dict) -> str:
    title    = topic.get("title", topic["topic"])
    hashtags = topic.get("hashtags", "#தெரியுமா #தமிழ் #வளர்ச்சி")
    return (
        f"உங்களுக்கு தெரியுமா? 🤔\n\n"
        f"✨ {title}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🔔 Follow @valarchi for daily Tamil facts\n"
        f"❤️  Share this with someone curious!\n\n"
        f"{hashtags} #valarchi #tamilfacts #தமிழ் #reels #didyouknow"
    )


# ─── MAIN ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Valarchi Daily Auto-Reel")
    parser.add_argument("--day",     type=int, default=None, help="Force day number")
    parser.add_argument("--dry-run", action="store_true",   help="Generate only, skip upload & post")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  VALARCHI DAILY AUTO-REEL  —  {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*55}\n")

    topics         = load_topics()
    state          = load_state()
    topic, day     = pick_topic(topics, state, force_day=args.day)

    # Fetch 5 different B-roll clips — Pexels first, Pixabay fallback
    bg_videos = fetch_broll(topic["topic"], count=5)

    if bg_videos:
        print(f"[bg] {len(bg_videos)} B-roll videos ready")
    else:
        print("[bg] No background videos — using gradient fallback")

    # ── 1. Generate video ───────────────────────────────────────────────
    video_path = gr.generate_reel(topic, bg_videos=bg_videos)

    if not video_path.exists():
        print("❌  Video generation failed!")
        sys.exit(1)

    size_mb = video_path.stat().st_size / 1_048_576
    print(f"\n📦  Video size: {size_mb:.1f} MB")

    # ── 2. Upload + post (unless dry-run) ──────────────────────────────
    if args.dry_run:
        print("\n🧪  DRY RUN — skipping upload and Instagram post.")
        print(f"    Video at: {video_path}")
    else:
        # Upload to R2
        public_url = upload_to_r2(video_path)

        # Build caption
        caption = build_caption(topic)
        print(f"\n📝  Caption preview:\n{caption[:200]}…\n")

        # Post to Instagram (skip gracefully if credentials are missing)
        ig_token = os.environ.get("IG_ACCESS_TOKEN", "")
        ig_user  = os.environ.get("INSTAGRAM_USER_ID", "")
        if ig_token and ig_user:
            result = post_to_instagram(public_url, caption)
            state["posted"].append({
                "day"     : day + 1,
                "topic_id": topic["id"],
                "topic"   : topic["topic"],
                "post_id" : result["post_id"],
                "date"    : datetime.now().isoformat(),
                "url"     : public_url,
            })
        else:
            print("\n⚠️  Instagram credentials not set — skipping post.")
            print(f"    🎬  Video available at: {public_url}")
            state["posted"].append({
                "day"     : day + 1,
                "topic_id": topic["id"],
                "topic"   : topic["topic"],
                "post_id" : None,
                "date"    : datetime.now().isoformat(),
                "url"     : public_url,
            })

    # ── 3. Advance day counter ──────────────────────────────────────────
    state["day"] = day + 1
    save_state(state)
    print(f"\n✅  Done! State saved. Next day: {state['day'] + 1}")


if __name__ == "__main__":
    main()
