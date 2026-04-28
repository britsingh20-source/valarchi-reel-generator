"""Quick test: generate reel for topic 1 (rubber) with gradient background."""
import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import generate_reel as gr
from pathlib import Path

with open('topics.json', encoding='utf-8') as f:
    topics = json.load(f)

topic = topics[0]  # rubber
print(f"Testing topic #{topic['id']}: {topic['topic']}")
print(f"Scenes: {len(topic['scenes'])}")

# No background video — gradient fallback
out = gr.generate_reel(topic, bg_video=None)
print(f"\nDone! Video: {out}")
print(f"Size: {out.stat().st_size / 1024 / 1024:.1f} MB")
