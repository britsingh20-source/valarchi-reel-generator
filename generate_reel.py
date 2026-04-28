"""
Valarchi-Style "Did You Know" Tamil Reel Generator
===================================================
Creates short-form vertical reels (1080x1920) with:
  - Real video background (or dark gradient fallback)
  - Tamil TTS voiceover via edge-tts (ta-IN-ValluvarNeural, male)
  - Word-by-word caption sync from edge-tts word boundaries
  - Lo-fi BGM mixed under the voice
  - VALARCHI branding at bottom
  - Saves to output/reel_dayXX.mp4
"""

import os, sys, json, random, glob, asyncio, subprocess, shutil, tempfile, platform
import textwrap
from pathlib import Path
from datetime import datetime
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── CONFIG ──────────────────────────────────────────────────────────────────
WIDTH        = 1080
HEIGHT       = 1920
FPS          = 30
VOICE        = "ta-IN-ValluvarNeural"
OUTPUT_DIR   = Path("output")
TEMP_DIR     = Path("temp")
BG_DIR       = Path("backgrounds")
FONT_DIR     = Path(__file__).parent / "fonts"
SAMPLE_RATE  = 44100

# Colours (VALARCHI gold palette)
CLR_BG_TOP      = (10, 10, 30)
CLR_BG_BOT      = (5, 5, 20)
CLR_CAPTION     = (255, 220, 80)    # gold
CLR_HIGHLIGHT   = (255, 255, 255)   # white for current word
CLR_SHADOW      = (0, 0, 0)
CLR_BRAND       = (255, 215, 0)
CLR_KNOW        = (255, 80, 80)     # red accent for "தெரியுமா?"

# ── FONT HELPERS ────────────────────────────────────────────────────────────
def find_tamil_font():
    candidates = [
        os.environ.get("VALARCHI_FONT_PATH", ""),
        str(FONT_DIR / "NotoSansTamil-Regular.ttf"),
        str(FONT_DIR / "NotoSansTamil-Bold.ttf"),
    ]
    # Search system paths
    for pattern in [
        "/usr/share/fonts/**/NotoSansTamil*.ttf",
        "/usr/share/fonts/**/Lohit-Tamil*.ttf",
        "C:/Windows/Fonts/NotoSansTamil*.ttf",
    ]:
        candidates += glob.glob(pattern, recursive=True)
    for p in candidates:
        if p and Path(p).exists():
            return p
    raise FileNotFoundError("No Tamil font found. Add NotoSansTamil-Regular.ttf to fonts/")

def find_latin_font():
    candidates = [
        str(FONT_DIR / "Poppins-Bold.ttf"),
        str(FONT_DIR / "Lato-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    for p in candidates:
        if p and Path(p).exists():
            return p
    # Last resort: use Tamil font for Latin too
    return find_tamil_font()

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

# ── TTS ─────────────────────────────────────────────────────────────────────
async def _generate_tts_async(text: str, audio_out: Path) -> list:
    """
    Run edge-tts with word boundary events.
    Returns list of {"word": str, "start": float, "end": float} in seconds.
    """
    import edge_tts
    word_times = []

    communicate = edge_tts.Communicate(text, VOICE)

    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            offset_s   = chunk["offset"]   / 10_000_000   # 100-ns units → seconds
            duration_s = chunk["duration"] / 10_000_000
            word_times.append({
                "word":  chunk["text"],
                "start": offset_s,
                "end":   offset_s + duration_s,
            })

    audio_out.parent.mkdir(parents=True, exist_ok=True)
    with open(audio_out, "wb") as f:
        for c in audio_chunks:
            f.write(c)

    return word_times


def run_tts(text: str, audio_out: Path) -> list:
    """Synchronous wrapper around async TTS."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _generate_tts_async(text, audio_out))
                return future.result()
        else:
            return loop.run_until_complete(_generate_tts_async(text, audio_out))
    except RuntimeError:
        return asyncio.run(_generate_tts_async(text, audio_out))


# ── BGM GENERATOR ───────────────────────────────────────────────────────────
def generate_bgm(duration_s: float, out_path: Path):
    """Generate a gentle lo-fi background music track using numpy."""
    sr = SAMPLE_RATE
    t  = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)

    # Chord tones: Am pentatonic feel
    freqs  = [220.0, 261.63, 329.63, 392.0, 440.0]
    track  = np.zeros_like(t)

    for i, freq in enumerate(freqs):
        phase  = random.uniform(0, np.pi)
        amp    = 0.12 / (i + 1)
        # Slow tremolo
        tremolo = 1 + 0.15 * np.sin(2 * np.pi * 0.5 * t)
        wave    = amp * tremolo * np.sin(2 * np.pi * freq * t + phase)
        track  += wave

    # Add soft hi-hat (white noise bursts every 0.5s)
    beat_sr  = int(sr * 0.5)
    for i in range(int(duration_s * 2)):
        start = i * beat_sr
        end   = start + int(sr * 0.05)
        if end < len(track):
            hihat = np.random.randn(end - start) * 0.015
            track[start:end] += hihat

    # Normalise
    track = track / (np.max(np.abs(track)) + 1e-8) * 0.4

    # Convert to 16-bit PCM and save as WAV
    pcm = (track * 32767).astype(np.int16)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import wave, struct
    with wave.open(str(out_path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# ── BACKGROUND FRAMES ───────────────────────────────────────────────────────
def extract_bg_frames(bg_video: Path, total_frames: int, w: int, h: int, out_dir: Path):
    """Batch-extract frames from a background video using ffmpeg."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_pattern = str(out_dir / "frame_%05d.jpg")
    fps_ratio = f"{total_frames}/{max(1, int(get_video_duration(bg_video)))}"
    cmd = [
        "ffmpeg", "-y", "-i", str(bg_video),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps_ratio}",
        "-q:v", "3",
        frame_pattern
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_video_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
           "-show_streams", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return float(stream.get("duration", 30))
    return 30.0


def make_gradient(w: int, h: int) -> np.ndarray:
    """Create a dark cinematic gradient as fallback background."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        ratio = y / h
        r = int(CLR_BG_TOP[0] * (1 - ratio) + CLR_BG_BOT[0] * ratio)
        g = int(CLR_BG_TOP[1] * (1 - ratio) + CLR_BG_BOT[1] * ratio)
        b = int(CLR_BG_TOP[2] * (1 - ratio) + CLR_BG_BOT[2] * ratio)
        frame[y, :] = [r, g, b]
    return frame


# ── FRAME RENDERER ──────────────────────────────────────────────────────────
def wrap_text(text: str, font, max_width: int, draw) -> list:
    """Wrap text so each line fits within max_width pixels."""
    words = text.split()
    lines, line = [], []
    for word in words:
        test = " ".join(line + [word])
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] > max_width and line:
            lines.append(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        lines.append(" ".join(line))
    return lines


def auto_font_size(text: str, tamil_font_path: str, max_width: int, max_height: int,
                   start_size=90) -> tuple:
    """Find largest font size that fits text in given dimensions."""
    img_dummy = Image.new("RGB", (max_width, max_height))
    draw = ImageDraw.Draw(img_dummy)
    size = start_size
    while size >= 36:
        font = load_font(tamil_font_path, size)
        lines = wrap_text(text, font, max_width - 40, draw)
        line_h = size + 10
        total_h = len(lines) * line_h
        max_line_w = max(
            draw.textbbox((0, 0), l, font=font)[2] - draw.textbbox((0, 0), l, font=font)[0]
            for l in lines
        ) if lines else 0
        if max_line_w <= max_width - 40 and total_h <= max_height:
            return font, lines
        size -= 6
    return load_font(tamil_font_path, 36), wrap_text(text, load_font(tamil_font_path, 36), max_width - 40, draw)


def render_frame(bg_array: np.ndarray, caption: str, scene_progress: float,
                 tamil_font_path: str, latin_font_path: str,
                 topic_title: str = "", is_first: bool = False,
                 use_english: bool = True) -> Image.Image:
    """
    Render a single video frame.
    bg_array: H×W×3 numpy array (RGB)
    caption: caption text for this scene (English or Tamil)
    scene_progress: 0.0–1.0 progress within scene (for animations)
    use_english: if True, use latin_font_path for rendering (clean English text)
    """
    img = Image.fromarray(bg_array.astype(np.uint8), "RGB")

    # Dark vignette overlay
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    for i in range(40):
        alpha = int(i * 3.5)
        vdraw.rectangle([i, i, WIDTH - i, HEIGHT - i], outline=(0, 0, 0, alpha))
    # Bottom gradient for text area
    for y in range(HEIGHT // 2, HEIGHT):
        ratio = (y - HEIGHT // 2) / (HEIGHT // 2)
        alpha = int(ratio * 170)
        vdraw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), vignette)

    draw = ImageDraw.Draw(img)

    # ── Caption text ───────────────────────────────────────────────────────
    text_zone_top    = HEIGHT // 2
    text_zone_height = int(HEIGHT * 0.35)
    text_zone_width  = int(WIDTH * 0.88)

    # Animate: fade-in + slight slide up
    anim_alpha = min(1.0, scene_progress * 4)   # fully visible in first 25% of scene
    slide_y    = int((1.0 - anim_alpha) * 30)

    # Use Latin font for English captions (renders cleanly), Tamil font otherwise
    caption_font_path = latin_font_path if use_english else tamil_font_path
    font, lines = auto_font_size(caption, caption_font_path,
                                  text_zone_width, text_zone_height, start_size=88)
    line_h   = int(font.size * 1.35)
    total_h  = len(lines) * line_h
    start_y  = text_zone_top + (text_zone_height - total_h) // 2 + slide_y

    for i, line in enumerate(lines):
        bb     = draw.textbbox((0, 0), line, font=font)
        lw     = bb[2] - bb[0]
        x      = (WIDTH - lw) // 2
        y      = start_y + i * line_h

        # Drop shadow (thicker for English for pop-out look)
        shadow_offset = max(3, font.size // 20)
        for dx, dy in [(shadow_offset, shadow_offset), (-shadow_offset, shadow_offset),
                       (shadow_offset, -shadow_offset), (0, shadow_offset + 1)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 220))

        # Main text with gold colour
        col_with_alpha = CLR_CAPTION + (int(255 * anim_alpha),)
        draw.text((x, y), line, font=font, fill=col_with_alpha)

    # ── VALARCHI brand ────────────────────────────────────────────────────
    _draw_brand(draw, latin_font_path, tamil_font_path)

    # ── First scene: show "DID YOU KNOW?" banner ──────────────────────────
    if is_first and scene_progress < 0.8:
        _draw_know_banner_en(draw, latin_font_path, scene_progress)

    return img.convert("RGB")


def _draw_brand(draw, latin_font_path: str, tamil_font_path: str):
    """Draw DID YOU KNOW? channel name at bottom of frame."""
    brand_size = 44
    icon_size  = 50
    brand_font = load_font(latin_font_path, brand_size)
    icon_font  = load_font(latin_font_path, icon_size)

    brand_text = "DID YOU KNOW?"
    icon_text  = "?"

    # Measure brand text only (clean single text approach)
    bb_brand = draw.textbbox((0, 0), brand_text, font=brand_font)
    bw = bb_brand[2] - bb_brand[0]
    cw = 0

    gap     = 0
    total_w = bw
    x_start = (WIDTH - total_w) // 2
    y       = HEIGHT - 108

    # Shadow
    draw.text((x_start + 3, y + 3), brand_text, font=brand_font, fill=(0, 0, 0, 200))

    # Brand text — bright gold
    draw.text((x_start, y), brand_text, font=brand_font, fill=CLR_BRAND)

    # Thin decorative line above brand
    line_y = y - 16
    line_half = min(int(bw // 2), 160)
    draw.line([(WIDTH // 2 - line_half, line_y), (WIDTH // 2 + line_half, line_y)],
              fill=CLR_BRAND, width=2)


def _draw_know_banner_en(draw, latin_font_path: str, progress: float):
    """Overlay 'DID YOU KNOW?' banner at top in first scene."""
    text  = "DID YOU KNOW?"
    size  = 72
    font  = load_font(latin_font_path, size)
    alpha = min(1.0, progress * 6)

    bb = draw.textbbox((0, 0), text, font=font)
    w  = bb[2] - bb[0]
    x  = (WIDTH - w) // 2
    y  = 140

    # Glow shadow
    for dx, dy in [(4, 4), (-4, 4), (4, -4), (-4, -4)]:
        draw.text((x + dx, y + dy), text, font=font, fill=(200, 40, 40, int(180 * alpha)))
    draw.text((x, y), text, font=font, fill=CLR_KNOW + (int(255 * alpha),))


# ── SCENE BUILDER FROM WORD TIMESTAMPS ─────────────────────────────────────
def build_scene_timeline(word_times: list, scenes_def: list) -> list:
    """
    Map word boundary timestamps to scenes.
    Each scene gets: start_time, end_time, caption.

    Strategy: distribute word_times evenly across scenes,
    using actual timestamps for start/end.
    """
    if not word_times:
        # Fallback: evenly spaced
        total = sum(s.get("duration", 3) for s in scenes_def)
        t = 0.0
        timeline = []
        for s in scenes_def:
            d = s.get("duration", 3)
            timeline.append({"start": t, "end": t + d, "caption": s["caption"]})
            t += d
        return timeline

    total_words = len(word_times)
    n_scenes    = len(scenes_def)
    audio_end   = word_times[-1]["end"] + 0.3

    # Distribute words proportionally by scene duration weights
    dur_weights = [s.get("duration", 3) for s in scenes_def]
    total_weight = sum(dur_weights)

    timeline = []
    word_idx = 0
    time_cursor = max(0.0, word_times[0]["start"] - 0.1)

    for i, scene in enumerate(scenes_def):
        frac       = dur_weights[i] / total_weight
        n_words_in = max(1, round(total_words * frac))
        end_idx    = min(word_idx + n_words_in, total_words)

        if i == n_scenes - 1:
            end_time = audio_end
        else:
            end_time = word_times[min(end_idx, total_words - 1)]["start"]

        timeline.append({
            "start":   time_cursor,
            "end":     max(time_cursor + 1.5, end_time),
            "caption": scene["caption"],
        })
        time_cursor = timeline[-1]["end"]
        word_idx    = end_idx

    return timeline


# ── MAIN PIPELINE ───────────────────────────────────────────────────────────
def generate_reel(topic_data: dict, bg_video: Path = None,
                  bg_videos: list = None, dry_run: bool = False) -> Path:
    """
    Full pipeline: TTS → frames → BGM → FFmpeg → MP4
    bg_video:  single background video (legacy)
    bg_videos: list of background videos, cycled every 4-5 seconds
    Returns path to generated MP4.
    """
    topic_id   = topic_data["id"]
    narration  = topic_data["narration"]
    scenes_def = topic_data["scenes"]
    hashtags   = topic_data.get("hashtags", "#தமிழ் #வளர்ச்சி")

    # Normalise bg_videos list
    if bg_videos and len(bg_videos) > 0:
        pass  # use as-is
    elif bg_video:
        bg_videos = [bg_video]
    else:
        bg_videos = []

    OUTPUT_DIR.mkdir(exist_ok=True)
    work_dir = TEMP_DIR / f"day_{topic_id:03d}"
    work_dir.mkdir(parents=True, exist_ok=True)

    tamil_font  = find_tamil_font()
    latin_font  = find_latin_font()
    print(f"[fonts] Tamil: {tamil_font}")
    print(f"[fonts] Latin: {latin_font}")

    # ── 1. TTS ────────────────────────────────────────────────────────────
    voice_path = work_dir / "voice.mp3"
    print(f"[tts] Generating voice for topic {topic_id}…")
    word_times = run_tts(narration, voice_path)
    print(f"[tts] Got {len(word_times)} word boundaries")

    # Determine total duration from TTS or scene fallback
    if word_times:
        total_duration = word_times[-1]["end"] + 0.8
    else:
        total_duration = sum(s.get("duration", 3) for s in scenes_def) + 1.0
    print(f"[tts] Total duration: {total_duration:.1f}s")

    # ── 2. Scene timeline — use English captions ────────────────────────
    # Build scenes with English captions (caption_en preferred)
    scenes_en = []
    for s in scenes_def:
        scenes_en.append({
            "caption":  s.get("caption_en") or s.get("caption", ""),
            "duration": s.get("duration", 3),
        })
    timeline = build_scene_timeline(word_times, scenes_en)

    # ── 3. BGM ───────────────────────────────────────────────────────────
    bgm_path = work_dir / "bgm.wav"
    print("[bgm] Generating background music…")
    generate_bgm(total_duration + 1.0, bgm_path)

    # ── 4. Background frames — cycle multiple B-roll videos ─────────────
    total_frames   = int(total_duration * FPS)
    BROLL_SWITCH_S = 4          # switch B-roll every 4 seconds
    BROLL_SWITCH_F = BROLL_SWITCH_S * FPS   # frames per B-roll clip

    # per_vid_frames: how many frames each video contributes
    # We build a flat list bg_frame_list[frame_idx] = Path to jpg
    bg_frame_list = []          # will have total_frames entries

    valid_videos = [v for v in bg_videos if v and Path(v).exists()]

    if valid_videos:
        print(f"[bg] {len(valid_videos)} B-roll video(s) — switching every {BROLL_SWITCH_S}s")
        segment_idx = 0
        fi = 0
        while fi < total_frames:
            seg_end   = min(fi + BROLL_SWITCH_F, total_frames)
            seg_len   = seg_end - fi
            vid       = valid_videos[segment_idx % len(valid_videos)]
            seg_dir   = work_dir / f"bgseg_{segment_idx:03d}"

            try:
                extract_bg_frames(vid, seg_len + 5, WIDTH, HEIGHT, seg_dir)
                seg_frames = sorted(seg_dir.glob("frame_*.jpg"))
                # Fill exactly seg_len entries (loop if video too short)
                for j in range(seg_len):
                    bg_frame_list.append(seg_frames[j % len(seg_frames)] if seg_frames else None)
                print(f"[bg] Segment {segment_idx}: {vid.name} ({seg_len} frames)")
            except Exception as e:
                print(f"[bg] Segment {segment_idx} failed: {e} — using gradient")
                for j in range(seg_len):
                    bg_frame_list.append(None)

            fi           += seg_len
            segment_idx  += 1
    else:
        print("[bg] No background videos — using gradient")
        bg_frame_list = [None] * total_frames

    # Ensure length matches
    while len(bg_frame_list) < total_frames:
        bg_frame_list.append(None)

    # ── 5. Render all frames ──────────────────────────────────────────────
    render_dir = work_dir / "render"
    render_dir.mkdir(exist_ok=True)
    print(f"[render] Rendering {total_frames} frames…")

    # Build per-frame scene lookup
    frame_scene = []
    for fi in range(total_frames):
        t = fi / FPS
        current  = timeline[-1]
        progress = 1.0
        for scene in timeline:
            if scene["start"] <= t < scene["end"]:
                current  = scene
                progress = (t - scene["start"]) / max(0.01, scene["end"] - scene["start"])
                break
        is_first = (fi == 0 and t < timeline[0]["end"])
        frame_scene.append((current["caption"], progress, is_first))

    # Gradient fallback
    gradient_bg = make_gradient(WIDTH, HEIGHT)

    for fi in range(total_frames):
        caption, progress, is_first = frame_scene[fi]

        # Get background from the pre-built list
        bg_path = bg_frame_list[fi] if fi < len(bg_frame_list) else None
        if bg_path and Path(bg_path).exists():
            bg_arr = np.array(Image.open(bg_path).resize((WIDTH, HEIGHT)))
        else:
            bg_arr = gradient_bg.copy()

        frame_img = render_frame(
            bg_arr, caption, progress,
            tamil_font, latin_font,
            topic_title=topic_data.get("title", ""),
            is_first=is_first,
            use_english=True,
        )
        frame_img.save(render_dir / f"f_{fi:05d}.jpg", quality=90)

        if fi % 60 == 0:
            print(f"[render] {fi}/{total_frames} frames done")

    # ── 6. Mix audio (voice + BGM) ────────────────────────────────────────
    mixed_audio = work_dir / "mixed.aac"
    print("[audio] Mixing voice + BGM…")
    mix_cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_path),
        "-i", str(bgm_path),
        "-filter_complex",
        "[0:a]volume=3.0[voice];[1:a]volume=0.4[bgm];[voice][bgm]amix=inputs=2:duration=first[out]",
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        str(mixed_audio)
    ]
    subprocess.run(mix_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ── 7. Assemble final video ───────────────────────────────────────────
    out_path = OUTPUT_DIR / f"reel_day{topic_id:03d}.mp4"
    print(f"[ffmpeg] Assembling {out_path.name}…")
    asm_cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(render_dir / "f_%05d.jpg"),
        "-i", str(mixed_audio),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        str(out_path)
    ]
    subprocess.run(asm_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"[done] Reel saved to {out_path}")

    # Clean up temp frames to save disk
    for seg_dir in work_dir.glob("bgseg_*"):
        shutil.rmtree(seg_dir, ignore_errors=True)
    shutil.rmtree(work_dir / "frames", ignore_errors=True)
    shutil.rmtree(render_dir, ignore_errors=True)

    return out_path


# ── CLI TEST ENTRY ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate a single Valarchi reel")
    parser.add_argument("--topic", type=int, default=1, help="Topic ID from topics.json")
    parser.add_argument("--bg",    type=str, default="",  help="Background video path")
    parser.add_argument("--dry-run", action="store_true", help="Skip upload/post")
    args = parser.parse_args()

    topics_file = Path(__file__).parent / "topics.json"
    with open(topics_file, encoding="utf-8") as f:
        topics = json.load(f)

    # Find topic by ID
    topic = next((t for t in topics if t["id"] == args.topic), None)
    if topic is None:
        print(f"Topic ID {args.topic} not found")
        sys.exit(1)

    bg = Path(args.bg) if args.bg else None
    if bg is None:
        # Auto-pick first video from backgrounds/
        vids = list(BG_DIR.glob("*.mp4")) + list(BG_DIR.glob("*.mov"))
        bg   = vids[0] if vids else None

    out = generate_reel(topic, bg_video=bg, dry_run=args.dry_run)
    print(f"\n✅ Video: {out}")
