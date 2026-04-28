import sys, os, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
os.environ['PIXABAY_API_KEY'] = '55263834-006817233c3830c9ba54290a6'
import daily_run as dr, generate_reel as gr
from pathlib import Path
with open('topics.json', encoding='utf-8') as f: topics=json.load(f)
topic=topics[0]
print('Scene EN:', topic['scenes'][0].get('caption_en','MISSING'))
bg_videos=dr.fetch_pixabay_broll(topic['topic'],count=5)
print('Got',len(bg_videos),'B-roll videos')
out=gr.generate_reel(topic,bg_videos=bg_videos)
print('Done:',out)
