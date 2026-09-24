import os
import sys
import json
import urllib.request
import base64

API_KEY = os.environ["GEMINI_API_KEY"]

VIDEO_PATH = sys.argv[1]

with open(VIDEO_PATH, "rb") as f:
    video_data = base64.b64encode(f.read()).decode("utf-8")

prompt = """
Analyze this video for an automated YouTube Shorts pipeline.

Find EVERY genuinely useful, interesting, funny, surprising, emotional,
informative, or highly engaging moment that could work as an independent
Short.

Do NOT create arbitrary clips just to increase the number of clips.

For every strong moment provide:
- start time in seconds
- end time in seconds
- why the moment is worth clipping
- a short hook/title

Return ONLY valid JSON in this exact format:

{
  "clips": [
    {
      "start": 0.0,
      "end": 30.0,
      "reason": "Why this moment is valuable",
      "hook": "Short hook"
    }
  ]
}
"""

url = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/gemini-3.5-flash-lite:generateContent?key="
    + API_KEY
)

payload = {
    "contents": [
        {
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "video/mp4",
                        "data": video_data
                    }
                }
            ]
        }
    ]
}

data = json.dumps(payload).encode("utf-8")

request = urllib.request.Request(
    url,
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)

with urllib.request.urlopen(request) as response:
    result = json.loads(response.read().decode())

text = result["candidates"][0]["content"]["parts"][0]["text"].strip()

print(text)

try:
    parsed = json.loads(text)
except json.JSONDecodeError:
    raise RuntimeError("Gemini did not return valid JSON")

with open("clips.json", "w", encoding="utf-8") as f:
    json.dump(parsed, f, indent=2, ensure_ascii=False)

print("VIDEO ANALYSIS COMPLETE")
