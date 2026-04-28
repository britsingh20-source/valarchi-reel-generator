import sys, os, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
os.environ['PIXABAY_API_KEY'] = '55263834-006817233c3830c9ba54290a6'
import daily_run as dr
import generate_reel as gr
from pathlib import Path

with open('topics.json', encoding='utf-8') as f:
    topics = json.load(f)
topic = topics[0]
bg = dr.fetch_pixabay_broll(topic['topic'])
print('BG video:', bg)
out = gr.generate_reel(topic, bg_video=bg)
print('Done:', out)
