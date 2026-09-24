import os
import sys
import json
import urllib.request

key = os.environ["GEMINI_API_KEY"]

if len(sys.argv) < 2:
    raise RuntimeError("Usage: python scripts/analyze_video.py <video_path>")

video_path = sys.argv[1]

if not os.path.exists(video_path):
    raise FileNotFoundError(video_path)

print(f"Video found: {video_path}")
print("Ready for Gemini video analysis.")
